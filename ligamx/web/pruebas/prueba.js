#!/usr/bin/env node
/* Pruebas de la página de Cerebro Liga MX con Playwright.

   Uso (desde cualquier carpeta):
     PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node web/pruebas/prueba.js chromium [--capturas]
     PLAYWRIGHT_BROWSERS_PATH=<carpeta con webkit> node web/pruebas/prueba.js webkit [--capturas]

   Reconstruye la página (construir.py --documento --salida web/), la abre con file:// desde web/ en
   iPhone 13 y en escritorio 1440x900 y revisa:
   - archivo: fragmento válido, tokens de color, sin scripts externos, capacidad "db" declarada y usada;
   - portada: foto del favorito con movimiento lento, trofeo con su escudo, confeti, nada encimado; en celular
     cabe completa en la primera pantalla (390x664, 360x700 y 375x620, con y sin la franja en vivo);
   - cuadro de la liguilla: 4 + 2 + 1 series con ida y vuelta. En celular, mini-cuadro del torneo (≤358 px de
     ancho) y lista vertical por ronda con botones pegajosos; en escritorio, tres columnas hasta 1399 px y
     espejo desde 1400, sin nada cortado a 1024, 1180, 1280, 1366, 1440 y 1920; detalle de la serie;
   - menú coherente con las secciones, pestañas, imágenes, textos sin "undefined"/"NaN"/"null";
   - en vivo con un window.claude simulado (db.doc("vivo/actual").onSnapshot): franja, minuto que avanza,
     gol nuevo con aviso, tabla al momento, documentos corruptos, límite de 10 s y página sin base de datos;
   - variantes: liguilla en curso (una ida jugada, una serie terminada), sin liguilla.torneo, datos
     opcionales en null, «vivo» incrustado, movimiento reducido.
   Con --capturas guarda PNG en web/pruebas/capturas/. Sale con código 1 si algo falla. */
'use strict';
const path = require('path');
const fs = require('fs');
const { execFileSync } = require('child_process');
let pw;
try { pw = require('playwright'); } catch (e) { pw = require('/opt/node-tools/node_modules/playwright'); }

const WEB = path.resolve(__dirname, '..');
const motor = (process.argv[2] || 'chromium').toLowerCase();
const CAPTURAS = process.argv.includes('--capturas');
const DIR_CAP = path.join(__dirname, 'capturas');
const URL_DOC = 'file://' + path.join(WEB, 'documento.html');
const EJEMPLO = JSON.parse(fs.readFileSync(path.join(WEB, '..', 'salidas', 'vivo_ejemplo.json'), 'utf8'));
const AHORA_EJEMPLO = '2026-11-21T23:41:30Z'; /* 10 s después de «generado_utc» del ejemplo */
const temporales = [];
const fallas = [];
let revisados = 0;

function revisa(cond, nombre, detalle) {
  revisados++;
  if (!cond) { fallas.push(nombre + (detalle ? ' → ' + detalle : '')); console.log('  FALLA  ' + nombre + (detalle ? ' → ' + detalle : '')); }
  else console.log('  ok     ' + nombre);
}
const copia = x => JSON.parse(JSON.stringify(x));

/* escribe una copia de documento.html con los datos incrustados cambiados por fn(d) */
function variante(nombre, fn) {
  const doc = fs.readFileSync(path.join(WEB, 'documento.html'), 'utf8');
  const re = /(<script type="application\/json" id="datos">)([\s\S]*?)(<\/script>)/;
  const d = JSON.parse(re.exec(doc)[2]);
  fn(d);
  const ruta = path.join(WEB, '_variante_' + nombre + '.html');
  fs.writeFileSync(ruta, doc.replace(re, (_, a, __, c) => a + JSON.stringify(d).replace(/<\//g, '<\\/') + c));
  temporales.push(ruta);
  return 'file://' + ruta;
}

/* liguilla en curso (una ida jugada, una serie terminada, una definida) y varios opcionales en null */
function conLiguillaEnCurso(d) {
  const t = d.liguilla.torneo, cu = t.rondas[0].series;
  d.liguilla.en_curso = true; t.estado = 'en_curso';
  const c1 = cu[0]; c1.real = true; c1.alternativas = [];
  Object.assign(c1.piernas[0], { id: 990000000, fecha_utc: '2026-11-26T03:00:00+00:00', fecha_local: '2026-11-25', hora_local: '21:00', jugado: true, gl: 1, gv: 0 });
  ['lam_l', 'lam_v', 'p_local', 'p_empate', 'p_visitante', 'marcador', 'marcadores'].forEach(k => delete c1.piernas[0][k]);
  Object.assign(c1.piernas[1], { id: 990000001, fecha_utc: '2026-11-29T01:00:00+00:00', fecha_local: '2026-11-28', hora_local: '19:00' });
  const c2 = cu[1]; c2.real = true; c2.decidida = true; c2.ganador = c2.mejor.equipo; c2.favorito = c2.ganador; c2.p_avanza_mejor = 1; c2.p_avanza_peor = 0; c2.alternativas = [];
  c2.piernas.forEach((l, i) => { Object.assign(l, { id: 990000010 + i, fecha_local: i ? '2026-11-29' : '2026-11-26', hora_local: '19:00', jugado: true, gl: i ? 2 : 0, gv: i ? 1 : 0 }); ['lam_l', 'lam_v', 'p_local', 'p_empate', 'p_visitante', 'marcador', 'marcadores'].forEach(k => delete l[k]); });
  c2.global = { probable: null, top: [], p_gana_mejor: null, p_empate: null, p_gana_peor: null };
  cu[2].real = true; cu[2].alternativas = null;
  const c4 = cu[3]; c4.global = null; c4.alternativas = null; c4.piernas[1].estadio = null; c4.piernas[0].marcador = null; c4.piernas[0].marcadores = null; c4.regla_empate = null;
  t.rondas[1].series[1].viene_de = null; t.rondas[1].fechas = null; t.nota = null;
  /* datos raros en el resto de la página: opcionales en null, ficha sin detalle, equipo sin escudo, sede sin fotos */
  const p0 = d.pendientes[0];
  p0.momios = null; p0.combinadas = null; p0.contexto = null; p0.explica = null; p0.mercados = null; p0.top5 = null; p0.lam_l = null;
  const p1 = d.pendientes[1];
  p1.combinadas.atrevida = null; p1.contexto.historial = null; p1.contexto.suspendidos_local = null; p1.contexto.sede = null; p1.estadio = { nombre: 'Sede nueva', ciudad: null, slug: 'no-existe', altitud_m: null };
  p1.fase = 'cuartos'; p1.pierna = 1; p1.etiqueta = 'Cuartos de final, ida'; p1.visitante = 'Equipo Nuevo';
  const p2 = d.pendientes[2];
  ['lam_l', 'lam_v', 'rho', 'top5', 'matriz', 'mercados', 'combinadas', 'explica', 'contexto', 'momios'].forEach(k => delete p2[k]); p2.detalle = false;
  d.combinada_jornada = null; d.calibracion_series = null; d.ultimos_resultados[0].pronostico = null;
  d.meta.modelo.contra_referencias = null; d.meta.modelo.seleccion = null; d.proyeccion.titulos = null;
  d.desempeno.acumulado = { n: 12, aciertos_1x2: 6, acierto_1x2: 0.5, marcadores_exactos: 2, marcador_exacto: 0.1667, logloss: 1.02, ee_logloss: 0.05, brier: 0.6, rps: 0.2,
    prob_media_del_pick: 0.47, logloss_referencia_tercios: 1.0986, combinadas: { segura: { n: 12, completas: 5, frecuencia: 0.4167, prob_anunciada: 0.45, picks_acertados_media: 3.1 } } };
  d.dominios = d.dominios.filter(x => !(x.a === 'América' && x.b === 'Cruz Azul'));
}

/* window.claude simulado: use("db") entrega una base cuyo doc().onSnapshot manda PRIMERO el documento vigente
   (el dado o el último que pasó la prueba) y luego lo que la prueba le pase con window.__vivo(doc, deCache).
   window.__err(codigo) mata al oyente con ese error, como hace la plataforma con un error terminal. */
function guionClaude(modo, doc) {
  return `(function () {
    var DOC = ${JSON.stringify(doc || null)}, sus = null, fallo = null;
    function foto(d, cache) { return { id: 'actual', exists: d != null, data: function () { return d == null ? undefined : d; }, metadata: { fromCache: !!cache, hasPendingWrites: false } }; }
    window.__subs = 0; window.__usos = 0;
    window.__vivo = function (d, cache) { if (!cache) DOC = d; if (sus) sus(foto(d, cache)); };
    window.__err = function (c) { var f = fallo; sus = null; fallo = null; if (f) f({ code: c }); };
    var db = { doc: function (ruta) { window.__ruta = ruta; return { onSnapshot: function (sig, err) { window.__subs++; sus = sig; fallo = err; setTimeout(function () { if (sus === sig) sig(foto(DOC, false)); }, 150); return function () { if (sus === sig) { sus = null; fallo = null; } }; } }; } };
    window.claude = { use: function (n) { window.__usos++; return new Promise(function (r) { ${modo === 'mudo' ? '' : `setTimeout(function () { r(${modo === 'nulo' ? 'null' : "n === 'db' ? db : null"}); }, 40);`} }); } };
  })();`;
}

async function textoVisible(page) {
  return page.evaluate(() => {
    document.querySelectorAll('details').forEach(d => { d.open = true; });
    document.querySelectorAll('[role="tabpanel"][hidden], #menu').forEach(e => { e.hidden = false; });
    const partes = ['#barra', '#menu', '#contenido', '.pie'].map(s => { const e = document.querySelector(s); return e ? e.innerText + ' ' + e.textContent : ''; });
    document.getElementById('menu').hidden = true;
    return partes.join('\n');
  });
}
function palabrasMalas(txt) {
  const m = txt.match(/.{0,40}(undefined|\bNaN\b|\bnull\b|\[object Object\]).{0,40}/);
  return m ? m[0].replace(/\s+/g, ' ') : null;
}
/* desbordes: ni el documento ni ningún elemento visible fuera de un contenedor con desplazamiento propio */
function desbordes(page) {
  return page.evaluate(() => {
    const ancho = window.innerWidth, malos = [];
    document.querySelectorAll('body *').forEach(e => {
      const r = e.getBoundingClientRect(); if (!r.width || !r.height) return;
      if (r.right > ancho + 1.5 || r.left < -1.5) {
        let p = e.parentElement, dentro = false;
        while (p && p !== document.body) { const o = getComputedStyle(p); if (/(auto|scroll|hidden|clip)/.test(o.overflowX)) { dentro = true; break; } p = p.parentElement; }
        if (!dentro) malos.push(e.tagName + '.' + String(e.className).slice(0, 40));
      }
    });
    return { sw: document.documentElement.scrollWidth, ancho, malos: malos.slice(0, 6) };
  });
}
/* portada en celular: titular, último título y las 4 probabilidades caben en la primera pantalla (el crédito puede quedar abajo) */
const TAMANOS_CELULAR = [[390, 664], [360, 700], [375, 620]];
async function primeraPantalla(page, vuelve, nombre) {
  for (const [w, h] of TAMANOS_CELULAR) {
    await page.setViewportSize({ width: w, height: h });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(300);
    const p = await page.evaluate(() => {
      const q = s => document.querySelector(s), b = s => { const e = q(s); return e ? e.getBoundingClientRect() : null; };
      const fav = b('#portada .favoritos'), tit = b('#portada .titular'), pal = b('#portada .palmares'), sello = b('#p-sello'), em = b('#portada .emblema'), fr = q('#franja');
      const piso = fr && !fr.hidden ? fr.getBoundingClientRect().bottom : b('#barra').bottom, rg = document.createRange();
      rg.selectNodeContents(q('#t-portada')); const tx = rg.getBoundingClientRect();
      return { alto: window.innerHeight, favoritos: Math.round(fav.bottom), n: document.querySelectorAll('#portada .favoritos li').length, sello: Math.round(sello.top), piso: Math.round(piso), franja: !!fr && !fr.hidden,
        titulo: [Math.round(tx.right), Math.round(em.left)], renglones: Math.round(b('#t-portada').height / parseFloat(getComputedStyle(q('#t-portada')).lineHeight)),
        orden: sello.top < tit.top && tit.bottom <= (pal ? pal.top : fav.top) + 1 && (!pal || pal.bottom <= fav.top + 1), y: window.pageYOffset };
    });
    revisa(p.y === 0 && p.n === 4 && p.favoritos <= p.alto - 12 && p.sello >= p.piso - 1 && p.orden && p.titulo[0] <= p.titulo[1] + 1 && p.renglones === 2,
      nombre + ' ' + w + 'x' + h + '): titular, favorito, último título y las 4 probabilidades caben en la primera pantalla', JSON.stringify(p));
  }
  await page.setViewportSize(vuelve);
  await page.waitForTimeout(300);
}
function abrir(ctx, errores) {
  return ctx.newPage().then(page => {
    page.on('console', m => { if (m.type() === 'error') errores.push(m.text() + ' @ ' + (m.location().url || '')); });
    page.on('pageerror', e => errores.push('pageerror: ' + e.message));
    return page;
  });
}

async function correr(navegador, nombre, opciones) {
  console.log('\n== ' + motor + ' · ' + nombre + ' ==');
  const movil = nombre === 'iphone';
  const ctx = await navegador.newContext(Object.assign({ ignoreHTTPSErrors: true, locale: 'es-MX' }, opciones));
  const errores = [];
  const page = await abrir(ctx, errores);
  let fuentes = true;
  page.on('requestfailed', r => { if (/fonts\.(googleapis|gstatic)\.com/.test(r.url())) fuentes = false; });
  await page.goto(URL_DOC, { waitUntil: 'load' });
  await page.waitForTimeout(700);
  const capDe = pg => async (archivo, op) => { if (CAPTURAS) { fs.mkdirSync(DIR_CAP, { recursive: true }); await pg.screenshot(Object.assign({ path: path.join(DIR_CAP, motor + '-' + nombre + '-' + archivo + '.png') }, op || {})); } };
  const capElDe = pg => async (archivo, sel, altoMax) => {
    if (!CAPTURAS) return;
    const el = pg.locator(sel).first(); await el.scrollIntoViewIfNeeded(); await pg.waitForTimeout(700);
    const b = await el.boundingBox(); if (!b) return;
    const y = await pg.evaluate(() => window.pageYOffset);
    await capDe(pg)(archivo, { fullPage: true, clip: { x: 0, y: Math.max(0, b.y + y - 8), width: pg.viewportSize().width, height: Math.min(altoMax || 1500, b.height + 16) } });
  };
  const cap = capDe(page), capEl = capElDe(page);

  /* ---------- portada ---------- */
  const por = await page.evaluate(async () => {
    const d = JSON.parse(document.getElementById('datos').textContent), m = JSON.parse(document.getElementById('medios').textContent);
    const im = document.querySelector('#portada .fondo img');
    for (let i = 0; i < 40 && !(im.complete && im.naturalWidth > 0); i++) await new Promise(r => setTimeout(r, 250));
    const cv = document.getElementById('confeti'), px = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data;
    let pintados = 0; for (let i = 3; i < px.length; i += 4) if (px[i] > 20) pintados++;
    const caja = s => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, r: r.right, b: r.bottom }; };
    const piezas = ['#p-sello', '#t-portada', '#portada .titular', '#portada .palmares', '#portada .favoritos', '#p-pie', '#portada .foto-de'].map(s => [s, caja(s)]).filter(x => x[1]);
    const encima = [];
    for (let i = 0; i < piezas.length; i++) for (let j = i + 1; j < piezas.length; j++) { const a = piezas[i][1], b = piezas[j][1]; if (a.x < b.r - 1 && b.x < a.r - 1 && a.y < b.b - 1 && b.y < a.b - 1) encima.push(piezas[i][0] + ' / ' + piezas[j][0]); }
    const em = caja('#portada .emblema'), tit = caja('#portada .titular'), barra = caja('#barra');
    if (em && tit && em.x < tit.r - 1 && tit.x < em.r - 1 && em.y < tit.b - 1 && tit.y < em.b - 1) encima.push('emblema / titular');
    if (em && barra && em.y < barra.b - 4) encima.push('emblema / barra');
    const fav = d.proyeccion.campeon[0].equipo, tit0 = ((d.proyeccion.titulos || {})[fav] || {}).ultimo;
    return { cargada: im.complete && im.naturalWidth > 0, src: im.getAttribute('src'), kb: im.classList.contains('kb'), anim: im.getAnimations ? im.getAnimations().length : -1,
      fav, titular: (document.querySelector('#portada .titular') || {}).textContent || '', equipoPortada: m.portada.equipo, escudo: !!document.querySelector('#emblema-esc img, #emblema-esc .esc'),
      trofeo: !!document.querySelector('#portada .emblema svg use') && !!document.getElementById('s-trofeo'), favoritos: document.querySelectorAll('#portada .favoritos li').length,
      palmares: (document.querySelector('#portada .palmares') || {}).textContent || '', debePalmares: !!(tit0 && tit0.torneo), torneoTitulo: tit0 ? tit0.torneo : '',
      credito: (document.querySelector('#portada .foto-de') || {}).textContent || '', confeti: pintados, encima, tono: document.getElementById('portada').getAttribute('data-tono'),
      reloj: !!document.querySelector('#reloj b') || !!document.querySelector('#reloj .nota') };
  });
  revisa(por.cargada && /^img\/(estadios|campeon)\//.test(por.src), 'portada: foto del favorito cargada (' + por.src + ')', JSON.stringify(por.src));
  revisa(por.kb && por.anim > 0, 'portada: la foto se mueve lento (Ken Burns)', 'animaciones: ' + por.anim);
  revisa(por.titular.includes(por.fav) && por.equipoPortada === por.fav && por.favoritos === 4, 'portada: titular, favorito (' + por.fav + ') y sus 4 probabilidades', JSON.stringify([por.titular, por.equipoPortada, por.favoritos]));
  revisa(por.escudo && por.trofeo, 'portada: trofeo dibujado con el escudo del favorito');
  revisa(por.confeti > 40, 'portada: confeti pintado en el lienzo', String(por.confeti));
  revisa(!por.debePalmares || por.palmares.includes(por.torneoTitulo), 'portada: leyenda con su último título (' + por.torneoTitulo + ')', por.palmares);
  revisa(/Foto/.test(por.credito) && por.credito.length > 12, 'portada: crédito de la foto visible', por.credito);
  revisa(por.encima.length === 0, 'portada: nada encimado', por.encima.join(' | '));
  revisa(por.reloj, 'portada: cuenta regresiva del próximo partido');
  await cap('1-portada');
  if (movil) await primeraPantalla(page, opciones.viewport, 'portada (celular');
  else {
    const pe = await page.evaluate(() => { const b = s => document.querySelector(s).getBoundingClientRect(), p = b('#portada'), tx = b('#b-portada'), em = b('#portada .emblema'), fav = b('#portada .favoritos'), rg = document.createRange(); rg.selectNodeContents(document.getElementById('t-portada')); const t = rg.getBoundingClientRect();
      return { alto: Math.round(p.height), pantalla: window.innerHeight, texto: Math.round(tx.width), copa: [Math.round(em.left), Math.round(em.right), Math.round(em.bottom)], titulo: [Math.round(t.left), Math.round(t.right)], fav: Math.round(fav.bottom), lado: document.getElementById('portada').getAttribute('data-lado') }; });
    revisa(pe.alto <= pe.pantalla + 1 && pe.texto <= 601 && (pe.copa[1] <= pe.titulo[0] || pe.copa[0] >= pe.titulo[1]) && Math.abs(pe.copa[2] - pe.fav) <= 2, 'portada (escritorio): cabe en la pantalla, el texto mide ≤600 px y la copa se para junto a las probabilidades sin tocar el título', JSON.stringify(pe));
  }

  /* ---------- estructura ---------- */
  const n = await page.evaluate(() => ({ tarjetas: document.querySelectorAll('.partido').length, pendientes: JSON.parse(document.getElementById('datos').textContent).pendientes.length,
    respaldos: document.querySelectorAll('.respaldo').length, estadios: document.querySelectorAll('.estadio').length, h1: document.querySelectorAll('h1').length,
    conexion: Array.from(document.querySelectorAll('.js-conexion')).map(e => e.textContent), franja: !document.getElementById('franja').hidden, vivo: !document.getElementById('vivo').hidden }));
  revisa(n.tarjetas === n.pendientes && n.tarjetas > 0, 'una tarjeta por partido pendiente', n.tarjetas + ' de ' + n.pendientes);
  revisa(n.respaldos === 0, 'ningún bloque en modo respaldo', String(n.respaldos));
  revisa(n.estadios === 16, 'galería con los 16 estadios', String(n.estadios));
  revisa(n.h1 === 1, 'un solo h1');
  revisa(!n.franja && !n.vivo && n.conexion.some(t => /^Sin conexión en vivo: datos (de las|del \d+ \w+,) \d\d:\d\d h \(centro de México\)/.test(t)), 'sin window.claude: la página funciona y lo dice (hora con zona; con fecha si no es de hoy)', JSON.stringify(n.conexion));

  /* ---------- cuadro de la liguilla ---------- */
  const cu = await page.evaluate(movil => {
    const t = JSON.parse(document.getElementById('datos').textContent).liguilla.torneo;
    const por = f => Array.from(document.querySelectorAll('.ronda[data-fase="' + f + '"] .llave'));
    const todas = Array.from(document.querySelectorAll('#cuadro .llave'));
    const sin = todas.filter(l => { const ps = l.querySelectorAll('.pierna'); return ps.length !== 2 || Array.from(ps).some(p => !p.querySelector('.tablero') || !p.querySelector('.x12') || !/Ida|Vuelta/.test(p.textContent)) || !l.querySelector('.avanza') || l.querySelectorAll('.llave__eq .esc').length !== 2; }).map(l => l.getAttribute('data-llave'));
    const c = document.getElementById('cuadro'), cs = getComputedStyle(c), nodo = document.querySelector(movil ? '.mn[data-p="a"]' : '.nodo[data-pos="a"]');
    const series = [].concat(...t.rondas.map(r => r.series));
    const sedes = series.every(s => { const l = document.querySelector('.llave[data-llave="' + s.llave + '"]'), sp = Array.from(l.querySelectorAll('.pierna__n span')).map(x => x.textContent); return s.piernas.every((p, i) => sp[i] && sp[i].startsWith(p.estadio.nombre.replace(/^Estadio\s+/i, '') + ' · ')); });
    const sinGlobal = todas.every(l => !/Global (más )?probable|Cierre probable/i.test(l.textContent) && !l.querySelector('.llave__global'));
    return { cuartos: por('cuartos').length, semis: por('semifinal').length, final: por('final').length, sin, sedes, sinGlobal, estado: t.estado,
      texto: document.querySelector('.cuadro-estado').textContent, campeon: (document.querySelector('.campeon-ruta b') || {}).textContent, campeonDato: t.campeon_ruta,
      trofeo: !!document.querySelector('.campeon-ruta svg use'), display: cs.display, sw: c.scrollWidth, cw: c.clientWidth,
      linea: nodo ? getComputedStyle(nodo, '::after').borderTopWidth : '', vieneDe: (document.querySelector('.llave[data-llave="S1"] .llave__id') || {}).textContent || '',
      dentro: todas.every(l => { const r = l.getBoundingClientRect(); return r.left >= -1 && r.right <= window.innerWidth + 1; }) };
  }, movil);
  revisa(cu.cuartos === 4 && cu.semis === 2 && cu.final === 1, 'cuadro: 4 series de cuartos, 2 semifinales y la final', JSON.stringify([cu.cuartos, cu.semis, cu.final]));
  revisa(cu.sin.length === 0, 'cuadro: cada serie trae ida y vuelta con marcador en tablero, 1X2 chico y barra de avance', cu.sin.join(','));
  revisa(cu.sinGlobal, 'cuadro: las tarjetas no llevan la fila «Global probable» (queda en el detalle)');
  revisa(cu.sedes, 'cuadro: cada partido dice su sede (sin el prefijo «Estadio») y su fecha');
  revisa(cu.campeon === cu.campeonDato && cu.trofeo, 'cuadro: termina en el campeón con su trofeo', cu.campeon + ' / ' + cu.campeonDato);
  revisa(cu.estado !== 'proyectado' || /si la tabla termina como se espera/i.test(cu.texto), 'cuadro: dice que es proyectado («si la tabla termina como se espera»)', cu.texto.slice(0, 80));
  revisa(parseFloat(cu.linea) >= 1.5 && /C\d y C\d/.test(cu.vieneDe), 'cuadro: líneas de unión y de qué llaves sale cada semifinal', cu.linea + ' · ' + cu.vieneDe);
  if (movil) {
    /* mini-cuadro: el torneo completo de un vistazo */
    const mini = await page.evaluate(() => {
      const t = JSON.parse(document.getElementById('datos').textContent).liguilla.torneo, me = JSON.parse(document.getElementById('medios').textContent).escudos;
      const abr = e => (me[e] && me[e].abr) || e.slice(0, 3).toUpperCase(), m = document.getElementById('mini-cuadro'), b = m.getBoundingClientRect(), malos = [];
      [].concat(...t.rondas.map(r => r.series)).forEach(s => {
        const n = m.querySelector('.mc[data-ver-llave="' + s.llave + '"]'); if (!n) { malos.push(s.llave + ' falta'); return; }
        const legs = Array.from(n.querySelectorAll('.mc__leg')).map(x => x.textContent.replace(/\s+/g, ' ').trim());
        const espera = s.piernas.map(l => (l.pierna === 2 ? 'VTA' : 'IDA') + abr(l.local) + ' ' + l.marcador.gl + '-' + l.marcador.gv + ' ' + abr(l.visitante));
        const pcts = Array.from(n.querySelectorAll('.mc__eq i')).map(x => x.textContent);
        if (n.querySelectorAll('.mc__eq .esc').length !== 2 || pcts.length !== 2 || !pcts.every(x => /^\d+%$/.test(x)) || JSON.stringify(legs) !== JSON.stringify(espera)) malos.push(s.llave + ' ' + JSON.stringify([pcts, legs]));
        if (Array.from(n.querySelectorAll('.mc__leg, .mc__eq b')).some(e => e.scrollWidth > e.clientWidth + 1)) malos.push(s.llave + ' cortado');
        if (n.tagName !== 'BUTTON' || n.getBoundingClientRect().height < 44) malos.push(s.llave + ' no es botón');
      });
      const x = k => Math.round(m.querySelector('.mc[data-ver-llave="' + k + '"]').getBoundingClientRect().left), linea = getComputedStyle(m.querySelector('.mn[data-p="s1"]'), '::before').borderTopWidth;
      return { ancho: Math.round(b.width), alto: Math.round(b.height), nodos: m.querySelectorAll('.mc').length, malos, columnas: x('C1') < x('S1') && x('S1') < x('F'), linea, dorado: getComputedStyle(m.querySelector('.mc__leg b')).color, blanco: getComputedStyle(document.body).color,
        campeon: (m.querySelector('.mc-campeon b') || {}).textContent, dato: t.campeon_ruta, trofeo: !!m.querySelector('.mc-campeon svg use'), pantalla: window.innerWidth };
    });
    revisa(mini.nodos === 7 && mini.malos.length === 0 && mini.columnas && parseFloat(mini.linea) >= 1.5 && mini.dorado !== mini.blanco, 'mini-cuadro (celular): 4 + 2 + 1 nodos en tres columnas, con escudos, % de avanzar e IDA y VUELTA en orden local–visitante', JSON.stringify(mini));
    revisa(mini.ancho <= 358 && mini.ancho <= mini.pantalla - 32 && mini.alto <= 440, 'mini-cuadro (celular): cabe en el ancho de la pantalla (≤358 px) y en ~430 px de alto', mini.ancho + ' x ' + mini.alto);
    revisa(mini.campeon === mini.dato && mini.trofeo, 'mini-cuadro (celular): la final termina en el trofeo y el campeón de la ruta', mini.campeon + ' / ' + mini.dato);
    /* debajo, las tarjetas en lista vertical por ronda */
    const lista = await page.evaluate(() => {
      const c = document.getElementById('cuadro'), rs = Array.from(c.querySelectorAll('.ronda')), ls = Array.from(c.querySelectorAll('.llave')).map(l => l.getBoundingClientRect()).sort((a, b) => a.top - b.top);
      let encima = 0, hueco = 0; for (let i = 1; i < ls.length; i++) { if (ls[i].top < ls[i - 1].bottom - 1) encima++; hueco = Math.max(hueco, ls[i].top - ls[i - 1].bottom); }
      return { rondas: rs.map(r => r.querySelector('.ronda__cab').textContent), orden: rs.every((r, i) => !i || r.getBoundingClientRect().top >= rs[i - 1].getBoundingClientRect().bottom - 1), encima, hueco: Math.round(hueco),
        anchas: ls.every(r => r.left >= 0 && r.right <= window.innerWidth + 1 && r.width >= window.innerWidth - 34), desliza: !!document.querySelector('.desliza') || /Desliza/i.test(document.getElementById('b-llaves').textContent),
        sw: c.scrollWidth, cw: c.clientWidth, alto: Math.round(Math.max(...ls.map(r => r.height))), pega: getComputedStyle(document.querySelector('.rondas-pega')).position };
    });
    revisa(lista.rondas.length === 3 && /Cuartos/.test(lista.rondas[0]) && /Semifinales/.test(lista.rondas[1]) && /Final/.test(lista.rondas[2]) && lista.orden && lista.encima === 0 && lista.anchas && lista.hueco < 110 && lista.alto < 280,
      'cuadro (celular): tarjetas en lista vertical agrupada por ronda, a todo el ancho y sin huecos muertos', JSON.stringify(lista));
    revisa(lista.sw <= lista.cw + 1 && !lista.desliza && /sticky/.test(lista.pega), 'cuadro (celular): sin desplazamiento horizontal ni aviso de deslizar', JSON.stringify([lista.sw, lista.cw, lista.desliza, lista.pega]));
    await page.evaluate(() => document.getElementById('mini-cuadro').scrollIntoView({ block: 'center' }));
    await page.waitForTimeout(300);
    await capEl('3a-mini-cuadro', '#mini-cuadro', 520);
    await page.click('.mc[data-ver-llave="C3"]');
    await page.waitForTimeout(1600);
    const toque = await page.evaluate(() => { const a = document.querySelector('.llave[data-llave="C3"]').getBoundingClientRect(), p = document.querySelector('.rondas-pega').getBoundingClientRect(), ba = document.getElementById('barra').getBoundingClientRect();
      return { top: Math.round(a.top), pega: [Math.round(p.top), Math.round(p.bottom)], barra: Math.round(ba.bottom), actual: document.querySelector('.rondas-nav [aria-current="true"]').textContent, x: window.pageXOffset, doc: document.documentElement.scrollWidth, ancho: window.innerWidth, hash: location.hash, marcadas: document.querySelectorAll('.llave--sel').length }; });
    revisa(toque.top >= toque.pega[1] - 1 && toque.top < toque.pega[1] + 60 && toque.hash === '' && toque.marcadas === 0, 'mini-cuadro (celular): tocar un nodo lleva a la tarjeta de esa serie', JSON.stringify(toque));
    revisa(Math.abs(toque.pega[0] - toque.barra) <= 2 && /Cuartos/.test(toque.actual) && toque.doc <= toque.ancho + 1 && toque.x === 0, 'cuadro (celular): los botones de ronda quedan pegajosos bajo la barra y el cuerpo no se mueve de lado', JSON.stringify(toque));
    await page.click('.rondas-nav button[data-ronda="2"]');
    await page.waitForTimeout(1600);
    const tr = await page.evaluate(() => { const f = document.querySelector('.llave[data-llave="F"]').getBoundingClientRect(), p = document.querySelector('.rondas-pega').getBoundingClientRect(), c = document.querySelector('.campeon-ruta').getBoundingClientRect();
      return { actual: document.querySelector('.rondas-nav [aria-current="true"]').textContent, finalVisible: f.top >= p.bottom - 1 && f.top < window.innerHeight * 0.6, campeonAbajo: c.top >= f.bottom - 1, pega: Math.round(p.top) }; });
    revisa(/Final/.test(tr.actual) && tr.finalVisible && tr.campeonAbajo, 'cuadro (celular): el botón «Final» lleva a la final (con el campeón al pie) y queda marcado', JSON.stringify(tr));
    await cap('3-cuadro-final');
  } else {
    revisa(cu.display === 'grid' && cu.dentro && cu.sw <= cu.cw + 1, 'cuadro (escritorio): horizontal completo, las 7 series a la vista', JSON.stringify([cu.display, cu.dentro, cu.sw, cu.cw]));
    const geo = await page.evaluate(() => { const r = k => document.querySelector('.llave[data-llave="' + k + '"]').getBoundingClientRect(); const f = r('F'), s1 = r('S1'), s2 = r('S2'), c = document.querySelector('.campeon-ruta').getBoundingClientRect(), rot = Array.from(document.querySelectorAll('.cuadro__rot')).map(e => e.getBoundingClientRect());
      const piezas = Array.from(document.querySelectorAll('.campeon-ruta > *')).map(e => e.getBoundingClientRect()), apilado = piezas.every((q, i) => !i || q.top >= piezas[i - 1].bottom - 1);
      return { centro: Math.abs((f.left + f.right) / 2 - window.innerWidth / 2), orden: s1.right < f.left && f.right < s2.left, campeonArriba: c.bottom <= f.top + 1, apilado, libre: rot.every(q => q.right < c.left || q.left > c.right || q.bottom < c.top) }; });
    revisa(geo.centro < 12 && geo.orden && geo.campeonArriba && geo.apilado && geo.libre, 'cuadro (escritorio): la final al centro, las semifinales a los lados y el campeón encima', JSON.stringify(geo));
    /* anchos de laptop y monitor: tres columnas hasta 1399 px, espejo desde 1400; nada cortado */
    for (const w of [1024, 1180, 1280, 1366, 1440, 1920]) {
      await page.setViewportSize({ width: w, height: w >= 1440 ? 900 : 768 });
      await page.waitForTimeout(300);
      const a = await page.evaluate(() => {
        const c = document.getElementById('cuadro'), b = c.getBoundingClientRect();
        const cort = Array.from(c.querySelectorAll('*')).filter(e => { const s = getComputedStyle(e); return e.clientWidth > 0 && e.scrollWidth > e.clientWidth + 1 && (s.textOverflow === 'ellipsis' || /hidden|clip/.test(s.overflowX)); }).map(e => String(e.className) + ': ' + e.textContent.slice(0, 24));
        const fuera = Array.from(c.querySelectorAll('.llave *')).filter(e => { const r = e.getBoundingClientRect(), l = e.closest('.llave').getBoundingClientRect(); return r.width > 0 && (r.right > l.right + 1 || r.left < l.left - 1); }).map(e => String(e.className));
        const pcts = Array.from(c.querySelectorAll('.pierna__x small')).every(sm => { const r = Array.from(sm.children).map(x => x.getBoundingClientRect()); return r.every((x, i) => !i || x.left >= r[i - 1].right + 3); });
        return { disp: getComputedStyle(c).display, alto: Math.round(b.height), sw: c.scrollWidth, cw: c.clientWidth, doc: document.documentElement.scrollWidth, cort: cort.slice(0, 4), fuera: fuera.slice(0, 4), pcts,
          mini: !!document.getElementById('mini-cuadro').offsetParent, pega: !!document.querySelector('.rondas-pega').offsetParent };
      });
      revisa(a.cort.length === 0 && a.fuera.length === 0 && a.pcts && a.sw <= a.cw + 1 && a.doc <= w + 1 && !a.mini && !a.pega && a.disp === (w >= 1400 ? 'grid' : 'flex'),
        'cuadro a ' + w + ' px: ' + (w >= 1400 ? 'en espejo' : 'tres columnas') + ', sin desplazamiento y sin nada cortado con puntos suspensivos ni fuera de su tarjeta', JSON.stringify(a));
      if (w === 1440) revisa(a.alto <= 900 - 60, 'cuadro en espejo a 1440x900: cabe en una pantalla', String(a.alto));
    }
    await page.setViewportSize(opciones.viewport);
    await page.waitForTimeout(300);
  }
  await capEl('3-cuadro', '#b-llaves', movil ? 1700 : 1000);

  /* detalle de la serie */
  const inv = await page.evaluate(() => { const d = document.getElementById('serie-det'); return d ? { invita: d.classList.contains('serie-det--invita'), chips: d.querySelectorAll('.serie-sel button').length, legs: d.querySelectorAll('.leg').length, marcadas: document.querySelectorAll('.llave--sel').length,
    caben: Array.from(d.querySelectorAll('.serie-sel button')).every(b => { const r = b.getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth && r.width >= 36; }), alto: Math.round(d.getBoundingClientRect().height) } : null; });
  revisa(inv && inv.invita && inv.chips === 7 && inv.caben && inv.legs === 0 && inv.marcadas === 0 && inv.alto < 330, 'detalle de la serie: al abrir invita a elegir (los 7 botones caben) y ninguna tarjeta queda marcada', JSON.stringify(inv));
  await page.click('.llave[data-llave="C1"] .llave__id b');
  await page.waitForTimeout(1300);
  const det0 = await page.evaluate(() => { const d = document.getElementById('serie-det'); return d ? { frase: /no es la suma de los dos marcadores/.test(d.textContent), led: !!d.querySelector('.serie-duelo .tablero'), global: (d.querySelector('.serie-duelo .vs > b') || {}).textContent || '', sale: Array.from(d.querySelectorAll('.lista li')).every(li => /sale en [\d.<]+%/.test(li.textContent)), volver: !!d.querySelector('[data-volver]'), titulo: d.querySelector('h3').textContent, legs: d.querySelectorAll('.leg').length, top: Array.from(d.querySelectorAll('.leg')).map(l => l.querySelectorAll('.top5 li').length), x12: d.querySelectorAll('.leg .x12').length, chips: d.querySelectorAll('.serie-sel button').length, alt: d.querySelectorAll('.lista li').length, sel: (document.querySelector('.llave--sel') || { getAttribute: () => null }).getAttribute('data-llave') } : null; });
  revisa(det0 && det0.legs === 2 && det0.top.every(x => x === 5) && det0.x12 === 2 && det0.chips === 7 && det0.alt >= 1 && det0.sel === 'C1' && det0.sale, 'detalle de la serie: ida y vuelta con los 5 marcadores más probables y los cruces alternativos («sale en…»)', JSON.stringify(det0));
  revisa(det0 && det0.frase && !det0.led && /^\d+-\d+$/.test(det0.global) && det0.volver, 'detalle de la serie: el global más probable va sin tablero, con la frase que lo explica, y hay botón para volver al cuadro', JSON.stringify(det0));
  await page.click('.llave[data-llave="S1"] .llave__id b');
  await page.waitForTimeout(1300);
  const det1 = await page.evaluate(() => { const d = document.getElementById('serie-det'), r = d.getBoundingClientRect(); return { titulo: d.querySelector('h3').textContent, sel: document.querySelector('.llave--sel').getAttribute('data-llave'), viene: (d.querySelector('.viene') || {}).textContent || '', top: Math.round(r.top), alto: window.innerHeight, hash: location.hash }; });
  revisa(det1.sel === 'S1' && det1.titulo !== det0.titulo && /resiembra/.test(det1.viene) && det1.top >= 0 && det1.top < det1.alto * 0.6 && det1.hash === '', 'tocar una serie del cuadro abre su detalle (dice de qué llaves viene y que hay resiembra)', JSON.stringify(det1));
  await page.click('.serie-sel button[data-serie="F"]');
  await page.waitForTimeout(300);
  const det2 = await page.evaluate(() => ({ titulo: document.querySelector('#serie-det h3').textContent, pres: document.querySelector('.serie-sel [aria-pressed="true"]').textContent, foco: document.activeElement && document.activeElement.getAttribute('data-serie') }));
  revisa(det2.pres === 'F' && det2.titulo !== det1.titulo && det2.foco === 'F', 'los botones del detalle cambian de serie sin perder el foco', JSON.stringify(det2));
  await capEl('3b-detalle', '#serie-det', 2800);
  await page.click('#serie-det [data-volver]');
  await page.waitForTimeout(1500);
  const vol = await page.evaluate(() => { const m = document.getElementById('mini-cuadro'), e = m.offsetParent ? m : document.getElementById('cuadro'), r = e.getBoundingClientRect(); return { top: Math.round(r.top), alto: window.innerHeight, hash: location.hash }; });
  revisa(vol.top >= 0 && vol.top < vol.alto * 0.5 && vol.hash === '', 'detalle de la serie: «Volver al cuadro» regresa al cuadro', JSON.stringify(vol));

  /* ---------- pestañas de la combinada del primer partido ---------- */
  const pest = await page.evaluate(() => {
    const tabs = Array.from(document.querySelectorAll('.partido [role="tab"]')).slice(0, 3);
    const panel = t => document.getElementById(t.getAttribute('aria-controls'));
    const antes = panel(tabs[0]).innerText;
    const vistos = [];
    for (const t of tabs.slice(1)) {
      t.click();
      vistos.push({ sel: t.getAttribute('aria-selected'), oculto: panel(t).hidden, otroOculto: panel(tabs[0]).hidden, distinto: panel(t).innerText !== antes && panel(t).innerText.length > 20 });
    }
    tabs[0].click();
    return { n: tabs.length, vistos, vuelve: !panel(tabs[0]).hidden };
  });
  revisa(pest.n === 3 && pest.vuelve && pest.vistos.every(v => v.sel === 'true' && !v.oculto && v.otroOculto && v.distinto), 'cada pestaña de la combinada cambia el contenido', JSON.stringify(pest));

  /* ---------- menú de tres barras ---------- */
  const men = await page.evaluate(() => {
    const items = Array.from(document.querySelectorAll('#menu li')).filter(li => !li.hidden).map(li => { const b = li.querySelector('[data-ir]'); return { ir: b.getAttribute('data-ir'), num: (b.querySelector('i') || {}).textContent || '' }; });
    const secciones = Array.from(document.querySelectorAll('main > section[id]')).filter(s => !s.hidden).map(s => s.id);
    const rotulos = {}; document.querySelectorAll('main > section[id] .rotulo').forEach(r => { const m = /^(\d\d)/.exec(r.textContent.trim()); if (m) rotulos[r.closest('section').id] = m[1]; });
    return { items, secciones, rotulos, barra: Array.from(document.querySelectorAll('.barra__nav li')).filter(li => !li.hidden).map(li => li.querySelector('[data-ir]').getAttribute('data-ir')) };
  });
  revisa(men.items.every(i => men.secciones.includes(i.ir)) && men.secciones.every(s => men.items.some(i => i.ir === s)), 'el menú lista exactamente las secciones que existen', JSON.stringify([men.items.map(i => i.ir), men.secciones]));
  revisa(men.items.every((i, k) => i.num === ('0' + k).slice(-2)) && men.items.every(i => !men.rotulos[i.ir] || men.rotulos[i.ir] === i.num) && men.barra.every(b => men.secciones.includes(b)), 'numeración del menú igual a la de las secciones', JSON.stringify([men.items.map(i => i.num), men.rotulos]));
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.click('#hamb');
  const abierto = await page.evaluate(() => ({ visible: !document.getElementById('menu').hidden, aria: document.getElementById('hamb').getAttribute('aria-expanded'), foco: document.activeElement && document.activeElement.closest('#menu') !== null }));
  revisa(abierto.visible && abierto.aria === 'true' && abierto.foco, 'el menú abre y toma el foco', JSON.stringify(abierto));
  await page.waitForTimeout(500); await cap('2-menu');
  await page.keyboard.press('Escape');
  revisa(await page.evaluate(() => document.getElementById('menu').hidden && document.activeElement.id === 'hamb'), 'Escape cierra el menú y devuelve el foco');
  await page.click('#hamb'); await page.click('#hamb');
  revisa(await page.evaluate(() => document.getElementById('menu').hidden), 'el botón cierra el menú');
  await page.click('#hamb');
  await page.click('#menu [data-ir="estadios"]');
  await page.waitForTimeout(1800);
  const tras = await page.evaluate(() => ({ cerrado: document.getElementById('menu').hidden, top: Math.round(document.getElementById('estadios').getBoundingClientRect().top), hash: location.hash }));
  revisa(tras.cerrado && Math.abs(tras.top) < 120 && tras.hash === '', 'elegir sección cierra el menú y desplaza sin tocar location.hash', JSON.stringify(tras));

  /* ---------- imágenes (recorre la página para disparar la carga diferida) ---------- */
  await page.evaluate(async () => {
    const paso = window.innerHeight * 0.9;
    for (let y = 0; y < document.documentElement.scrollHeight; y += paso) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 60)); }
    document.querySelectorAll('img').forEach(i => { i.loading = 'eager'; });
    await Promise.all(Array.from(document.images).map(i => i.complete ? null : new Promise(r => { i.onload = i.onerror = r; setTimeout(r, 8000); })));
    window.scrollTo(0, 0);
  });
  const imgs = await page.evaluate(() => { const t = Array.from(document.images); return { total: t.length, rotas: t.filter(i => !(i.complete && i.naturalWidth > 0)).map(i => i.getAttribute('src')), sinAlt: t.filter(i => !i.hasAttribute('alt')).length }; });
  revisa(imgs.total > 60 && imgs.rotas.length === 0, 'ninguna imagen rota (' + imgs.total + ')', imgs.rotas.slice(0, 5).join(', '));
  revisa(imgs.sinAlt === 0, 'todas las imágenes tienen atributo alt');
  const gal = await page.evaluate(() => { const b = document.querySelectorAll('.estadio [data-foto]')[1]; const im = b.closest('figure').querySelector('img'); const a = im.getAttribute('src'); b.click(); return { cambia: im.getAttribute('src') !== a, pres: b.getAttribute('aria-pressed') }; });
  revisa(gal.cambia && gal.pres === 'true', 'la galería de estadios cambia de foto');

  /* capturas de secciones */
  await page.evaluate(() => { const d = document.querySelector('.partido details'); if (d) d.open = true; });
  await capEl('4-partido', '.partido', 2600);
  await capEl('5-camino', '#b-campeon', 1300);
  await capEl('5b-cruces', '#b-cruces', 1500);
  await capEl('6-tabla', '#b-tabla', 1300);
  await capEl('7-estadios', '#b-estadios', 1500);
  await capEl('8-modelo', '#b-fuerzas', 1400);

  const desb = await desbordes(page);
  revisa(desb.sw <= desb.ancho + 1, 'sin desplazamiento horizontal del cuerpo', desb.sw + ' > ' + desb.ancho);
  revisa(desb.malos.length === 0, 'ningún elemento se sale de la pantalla', desb.malos.join(' | '));
  const mala = palabrasMalas(await textoVisible(page));
  revisa(!mala, 'sin "undefined", "NaN" ni "null" en el texto', mala || '');
  revisa(errores.length === 0, 'sin errores de consola ni pageerror', errores.slice(0, 4).join(' || '));
  if (!fuentes) console.log('  nota   las fuentes de Google no cargaron en esta máquina: se probó con la pila de respaldo');
  else console.log('  nota   fuente de titulares cargada: ' + await page.evaluate(() => document.fonts.check('900 40px "Big Shoulders Display"')));
  await page.close();

  /* ---------- EN VIVO con la base simulada ---------- */
  const errV = [];
  const pv = await abrir(ctx, errV);
  await pv.clock.install({ time: new Date(AHORA_EJEMPLO) });
  await pv.addInitScript(guionClaude('db', EJEMPLO));
  await pv.goto(URL_DOC, { waitUntil: 'load' });
  await pv.waitForTimeout(900);
  await pv.evaluate(() => { window.__marca = 1; });
  const idJ = EJEMPLO.partidos[0].id, idF = EJEMPLO.partidos.filter(p => p.estado === 'final')[0].id;
  const estado = () => pv.evaluate(([idJ, idF]) => {
    const fr = document.getElementById('franja'), q = (s, r) => (r || document).querySelector(s), t = e => e ? e.textContent : '';
    const b = q('.fr[data-ir="p-' + idJ + '"]'), tar = q('#p-' + idJ + ' [data-pvivo]'), fin = q('#p-' + idF + ' [data-pvivo]');
    return { franja: !fr.hidden, top: Math.round(fr.getBoundingClientRect().top), barra: Math.round(document.getElementById('barra').getBoundingClientRect().bottom), botones: fr.querySelectorAll('.fr').length, pulso: !!q('.franja .pulso'),
      minuto: t(q('.fr__min', b)), marcador: b ? Array.from(b.querySelectorAll('.tablero b')).map(x => x.textContent).join('-') : '', escudos: b ? b.querySelectorAll('.esc').length : 0,
      conexion: Array.from(document.querySelectorAll('.js-conexion')).map(e => e.textContent), modo: (q('.js-conexion') || { getAttribute: () => '' }).getAttribute('data-modo'),
      subs: window.__subs, usos: window.__usos, ruta: window.__ruta, marca: window.__marca,
      seccion: !document.getElementById('vivo').hidden, marcs: document.querySelectorAll('.marc').length, filas: document.querySelectorAll('#b-vivo-tabla tbody tr').length, enJuego: document.querySelectorAll('#b-vivo-tabla tr.enjuego').length,
      flechas: document.querySelectorAll('#b-vivo-tabla .mov').length, deltas: document.querySelectorAll('#b-vivo-proy .dl').length, listas: document.querySelectorAll('#b-vivo-proy .barras').length,
      navVivo: Array.from(document.querySelectorAll('.js-nav-vivo')).every(e => !e.hidden),
      tarjeta: !!tar && !tar.hidden, eventos: tar ? tar.querySelectorAll('.ev').length : 0, jugadores: tar ? t(q('.eventos', tar)) : '', barras: tar ? tar.querySelectorAll('.x12').length : 0, previo: tar ? /antes del partido/i.test(tar.textContent) : false, minTarjeta: tar ? t(q('.pvivo__min', tar)) : '',
      final: !!fin && !fin.hidden && /Resultado (acertado|fallado)/.test(fin.textContent) && !!fin.querySelector('.tablero--real'), cambia: document.querySelectorAll('.tablero b.cambia').length,
      guiones: Array.from(document.querySelectorAll('#b-vivo-tabla .mov')).filter(m => /[–—-]/.test(m.textContent)).length, pts: /\bpts\b/i.test(t(q('#b-vivo-proy')) + (tar ? tar.textContent : '')),
      flechas2: Array.from(document.querySelectorAll('#b-vivo-proy .dl, #p-' + idJ + ' .dl')).every(x => /^([▲▼] \d+\.\d|=)$/.test(x.textContent)), notaPP: /puntos porcentuales/.test(t(q('#b-vivo-proy'))) && (!tar || /puntos porcentuales/.test(tar.textContent)),
      finUna: !!fin && !/Resultado final/i.test(t(q('.pvivo__cab', fin))) && /Final/.test(t(q('.pvivo__cab', fin))),
      aviso: document.getElementById('aviso').hidden ? '' : document.getElementById('aviso').textContent, voz: document.getElementById('aviso-voz').textContent, respaldos: document.querySelectorAll('.respaldo').length };
  }, [idJ, idF]);
  let e1 = await estado();
  revisa(e1.franja && e1.botones === 2 && e1.pulso && e1.escudos === 2 && e1.marcador === '1-1' && e1.top >= e1.barra - 2 && e1.top < e1.barra + 6, 'en vivo: franja bajo la barra con escudos, marcador en tablero y punto que late', JSON.stringify(e1));
  revisa(e1.subs === 1 && e1.ruta === 'vivo/actual' && e1.usos === 1, 'en vivo: una sola suscripción a db.doc("vivo/actual")', JSON.stringify([e1.subs, e1.ruta, e1.usos]));
  revisa(e1.minuto === "57'" && e1.minTarjeta === "57'", 'en vivo: el minuto sale del documento', e1.minuto + ' / ' + e1.minTarjeta);
  revisa(e1.conexion.some(t => /^En vivo · actualizado (ahora mismo|hace \d+ s)/.test(t)) && e1.modo === 'vivo', 'en vivo: indicador de conexión («En vivo · actualizado hace…»)', JSON.stringify(e1.conexion));
  revisa(e1.tarjeta && e1.eventos === 3 && /Paulinho/.test(e1.jugadores) && /Marcel Ruiz/.test(e1.jugadores) && e1.barras === 2 && e1.previo, 'en vivo: la tarjeta trae marcador, eventos con jugador y la probabilidad al momento contra el pronóstico previo', JSON.stringify([e1.tarjeta, e1.eventos, e1.barras, e1.previo]));
  revisa(e1.final, 'en vivo: al terminar, resultado final y si el pronóstico acertó');
  revisa(e1.seccion && e1.marcs === EJEMPLO.partidos.length && e1.filas === EJEMPLO.tabla.length && e1.enJuego === EJEMPLO.tabla.filter(r => r.en_juego).length && e1.flechas === e1.filas && e1.listas === 2 && e1.deltas >= 8 && e1.navVivo, 'en vivo: tabla al momento (flechas, equipos en juego) y probabilidades con su cambio', JSON.stringify([e1.seccion, e1.marcs, e1.filas, e1.enJuego, e1.flechas, e1.listas, e1.deltas, e1.navVivo]));
  revisa(e1.guiones === 0 && e1.finUna, 'en vivo: sin guiones junto a la posición cuando no hay cambio y una sola etiqueta «Final» en el partido terminado', JSON.stringify([e1.guiones, e1.finUna]));
  revisa(!e1.pts && e1.flechas2 && e1.notaPP, 'en vivo: los cambios de probabilidad van con flecha y cifra («▲ 8.0») y una nota de «puntos porcentuales», sin «pts»', JSON.stringify([e1.pts, e1.flechas2, e1.notaPP]));
  const fj = await pv.evaluate(() => { const ba = document.getElementById('barra'); ba.style.transition = 'none'; void ba.offsetWidth; /* sin esperar la transición del fondo */
    const li = document.getElementById('franja-lista').getBoundingClientRect(), ex = document.getElementById('franja-extra'), xr = ex.getBoundingClientRect(), fr = document.getElementById('franja').getBoundingClientRect(), bs = Array.from(document.querySelectorAll('#franja .fr')).map(b => b.getBoundingClientRect());
    return { lista: Math.round(li.right), ancho: window.innerWidth, extra: xr.width > 0 ? ex.textContent : '', extraDer: Math.round(xr.right), alto: Math.round(fr.height), fondo: getComputedStyle(document.getElementById('franja')).backgroundColor, barra: getComputedStyle(document.getElementById('barra')).backgroundColor, cuerpo: getComputedStyle(document.body).backgroundColor, ultima: Math.round(bs[bs.length - 1].right) }; });
  revisa(fj.fondo === fj.cuerpo && fj.barra === fj.cuerpo, 'en vivo: la barra y la franja son opacas (nada se transparenta detrás)', JSON.stringify([fj.fondo, fj.barra, fj.cuerpo]));
  if (movil) {
    revisa(fj.lista >= fj.ancho - 1 && !fj.extra, 'en vivo (celular): la lista de la franja llega al borde de la pantalla', JSON.stringify(fj));
    await primeraPantalla(pv, opciones.viewport, 'portada con franja en vivo (celular');
  } else {
    revisa(/Marcel Ruiz/.test(fj.extra) && /Sigue: Pumas–Monterrey 19:00 h/.test(fj.extra) && fj.extraDer > fj.ancho * 0.7, 'en vivo (escritorio): la franja se llena con el último evento y el partido que sigue', JSON.stringify(fj));
    const ms = await pv.evaluate(() => Array.from(document.querySelectorAll('.marc')).map(m => { const b = m.getBoundingClientRect(), k = m.querySelector('.llave__ver'), kb = k.getBoundingClientRect(); return { top: Math.round(b.top), alto: Math.round(b.height), pie: Math.round(b.bottom - kb.bottom), letra: parseFloat(getComputedStyle(k).fontSize), der: Math.round(b.right - kb.right) }; }));
    revisa(ms.length === 4 && ms.every(m => m.top === ms[0].top && m.alto === ms[0].alto && m.pie <= 16 && m.pie >= 0 && m.letra >= 9 && m.der <= 16), 'en vivo (escritorio): las 4 tarjetas de «Al momento» en una fila, con «Ver el partido» legible y anclado abajo', JSON.stringify(ms));
    await pv.setViewportSize({ width: 1160, height: 800 });
    await pv.waitForTimeout(300);
    const nv = await pv.evaluate(() => { const h = document.getElementById('hamb').getBoundingClientRect(), n = document.querySelector('.barra__nav').getBoundingClientRect(), m = document.querySelector('#barra .marca').getBoundingClientRect(); return { hamb: Math.round(h.right), nav: [Math.round(n.left), Math.round(n.right)], marca: Math.round(m.right), ancho: window.innerWidth, sw: document.documentElement.scrollWidth, items: Array.from(document.querySelectorAll('.barra__nav li')).filter(li => !li.hidden).length }; });
    revisa(nv.items === 10 && nv.hamb <= nv.ancho && nv.nav[0] >= nv.marca && nv.nav[1] <= nv.ancho - 48 && nv.sw <= nv.ancho + 1, 'en vivo (1160 px): con «Al momento» en la navegación la hamburguesa sigue dentro de la pantalla', JSON.stringify(nv));
    await pv.setViewportSize({ width: 900, height: 800 });
    await pv.waitForTimeout(300);
    const m2 = await pv.evaluate(() => Array.from(document.querySelectorAll('.marc')).map(m => Math.round(m.getBoundingClientRect().left)));
    revisa(m2.length === 4 && m2[0] === m2[2] && m2[1] === m2[3] && m2[0] < m2[1], 'en vivo (900 px): las 4 tarjetas de «Al momento» en 2 x 2, sin huérfanas', JSON.stringify(m2));
    await pv.setViewportSize(opciones.viewport);
    await pv.waitForTimeout(300);
  }
  await capDe(pv)('9-vivo-franja');
  await capElDe(pv)('9b-vivo-seccion', '#vivo', 3400);
  await capElDe(pv)('9c-vivo-tarjeta', '#p-' + idJ, 1300);
  await pv.evaluate(() => window.scrollTo(0, 0));

  await pv.clock.fastForward(120000);
  await pv.waitForTimeout(150);
  let e2 = await estado();
  revisa(e2.minuto === "59'" && e2.minTarjeta === "59'", 'en vivo: el minuto avanza solo en la página (57\' → 59\')', e2.minuto + ' / ' + e2.minTarjeta);
  revisa(e2.conexion.some(t => /hace 2 min/.test(t)), 'en vivo: la antigüedad de los datos se actualiza', JSON.stringify(e2.conexion));

  await pv.click('.fr[data-ir="p-' + idJ + '"]');
  await pv.waitForTimeout(1600);
  const ida = await pv.evaluate(id => { const r = document.getElementById('p-' + id).getBoundingClientRect(), f = document.getElementById('franja').getBoundingClientRect(); return { top: Math.round(r.top), bajoFranja: r.top >= f.bottom - 2, alto: window.innerHeight }; }, idJ);
  revisa(ida.top < ida.alto * 0.5 && ida.bajoFranja, 'en vivo: tocar la franja lleva a la tarjeta del partido', JSON.stringify(ida));

  /* llega un gol */
  const gol = copia(EJEMPLO);
  gol.generado_utc = '2026-11-21T23:44:10Z';
  Object.assign(gol.partidos[0], { gl: 2, minuto: 60, reloj_utc: '2026-11-21T23:44:05Z' });
  gol.partidos[0].eventos.push({ min: 60, anadido: null, tipo: 'gol', equipo: 'Pachuca', jugador: 'Oussama Idrissi', marcador: '2-1' });
  gol.partidos[0].vivo = { p_local: 0.8312, p_empate: 0.1321, p_visitante: 0.0367, goles_restantes_l: 0.66, goles_restantes_v: 0.3, marcador_final: { gl: 2, gv: 1, prob: 0.3712 } };
  gol.tabla.forEach(r => { if (r.equipo === 'Pachuca') { r.PTS = 24; r.cambio = 2; } });
  gol.ultimo_evento = { utc: '2026-11-21T23:44:08Z', tipo: 'gol', partido_id: idJ, texto: "Gol de Pachuca (60'): Oussama Idrissi. Pachuca 2-1 Toluca" };
  await pv.evaluate(d => window.__vivo(d, false), gol);
  await pv.waitForTimeout(250);
  let e3 = await estado();
  revisa(e3.marcador === '2-1' && e3.eventos === 4 && /Idrissi/.test(e3.jugadores), 'en vivo: con el gol cambia el marcador y se suma el evento', e3.marcador + ' · ' + e3.eventos);
  revisa(/Gol de Pachuca/.test(e3.aviso) && e3.voz === e3.aviso, 'en vivo: aviso breve del evento nuevo (visible y en aria-live)', JSON.stringify([e3.aviso, e3.voz]));
  revisa(e3.cambia >= 2, 'en vivo: el marcador que cambió se anima', String(e3.cambia));
  revisa(e3.subs === 1 && e3.marca === 1, 'en vivo: sigue la misma suscripción y la página no se recargó', JSON.stringify([e3.subs, e3.marca]));
  await capDe(pv)('9d-vivo-gol');
  await pv.evaluate(() => { document.getElementById('aviso').hidden = true; });
  await pv.evaluate(d => window.__vivo(d, false), EJEMPLO);          /* llega tarde la foto anterior (1-1, de hace 3 min) */
  await pv.waitForTimeout(200);
  const e3b = await estado();
  revisa(e3b.marcador === '2-1' && e3b.eventos === 4 && !e3b.aviso && e3b.respaldos === 0, 'en vivo: un documento más viejo que el vigente se ignora (ni regresa el marcador ni repite el aviso)', JSON.stringify([e3b.marcador, e3b.eventos, e3b.aviso]));

  /* liguilla en vivo: el cuadro muestra el global y la probabilidad de avanzar al momento */
  const lig = copia(gol);
  lig.generado_utc = '2026-11-21T23:45:00Z';
  const cuHoy = await pv.evaluate(() => JSON.parse(document.getElementById('datos').textContent).liguilla.torneo.rondas[0].series.map(x => ({ llave: x.llave, mejor: x.mejor.equipo, peor: x.peor.equipo })));
  const C1 = cuHoy.filter(x => x.llave === 'C1')[0], C2 = cuHoy.filter(x => x.llave === 'C2')[0];
  lig.series = [{ llave: 'C1', fase: 'cuartos', mejor: { equipo: C1.mejor, siembra: 1 }, peor: { equipo: C1.peor, siembra: 8 }, piernas: [{ pierna: 1, id: 1, local: C1.peor, visitante: C1.mejor, estado: 'en_juego', gl: 0, gv: 1 }, { pierna: 2, id: 2, local: C1.mejor, visitante: C1.peor, estado: 'programado', gl: null, gv: null }], global_mejor: 1, global_peor: 0, p_avanza_mejor: 0.8731, p_avanza_peor: 0.1269, decidida: false, ganador: null, al_momento: true },
    { llave: 'C2', fase: 'cuartos', mejor: { equipo: C2.mejor, siembra: 2 }, peor: { equipo: C2.peor, siembra: 7 }, global_mejor: 0, global_peor: 0, p_avanza_mejor: 0.84, p_avanza_peor: 0.16, al_momento: false }];
  lig.partidos[0].serie = { llave: 'C1', mejor: C1.mejor, peor: C1.peor, global_mejor: 1, global_peor: 0, p_avanza_mejor: 0.8731, p_avanza_peor: 0.1269 };
  await pv.evaluate(d => window.__vivo(d, false), lig);
  await pv.waitForTimeout(200);
  const lv = await pv.evaluate(() => { const e = document.querySelector('[data-vivo-serie="C1"]'), o = document.querySelector('[data-vivo-serie="C2"]'), a = e.closest('.llave'), n1 = document.querySelector('.mc[data-ver-llave="C1"]'), n2 = document.querySelector('.mc[data-ver-llave="C2"]'), an = a.querySelector('.llave__antes');
    return { visible: !e.hidden, texto: e.textContent, tablero: Array.from(e.querySelectorAll('.tablero b')).map(b => b.textContent).join('-'), otra: o.hidden,
      atenuado: a.classList.contains('llave--vivo') && getComputedStyle(an).display !== 'none' && /antes del partido/i.test(an.textContent) && !o.closest('.llave').classList.contains('llave--vivo'), junto: e.querySelector('.chip--vivo').nextElementSibling === e.querySelector('.pm'),
      mini: { punto: !!n1.querySelector('.mc__vivo'), real: Array.from(n1.querySelectorAll('.mc__leg.real')).map(x => x.textContent), pct: Array.from(n1.querySelectorAll('.mc__eq i')).map(x => x.textContent), otro: !!n2.querySelector('.mc__vivo') || n2.querySelectorAll('.mc__leg.real').length } }; });
  revisa(lv.visible && /Al momento/.test(lv.texto) && lv.tablero === '1-0' && /87%/.test(lv.texto) && lv.otra, 'en vivo: el cuadro muestra el global y la probabilidad de avanzar al momento', JSON.stringify(lv));
  revisa(lv.atenuado && lv.junto, 'en vivo: en la tarjeta de la serie el tablero va junto a «Al momento» y los % previos quedan atenuados y rotulados «antes del partido»', JSON.stringify(lv));
  revisa(lv.mini.punto && lv.mini.real.length === 1 && /^IDA\w+ 0-1 \w+$/.test(lv.mini.real[0]) && lv.mini.pct.join() === '87%,13%' && !lv.mini.otro, 'en vivo: el mini-cuadro marca la serie en juego (punto rojo, marcador real en blanco y % al momento)', JSON.stringify(lv.mini));
  await capElDe(pv)('9e-vivo-cuadro', '.llave[data-llave="C1"]', 600);
  /* H10: la pierna en juego con su marcador real, el detalle de la serie al momento, y otra serie con la misma llave no se pinta */
  await pv.evaluate(() => document.querySelector('.serie-sel [data-serie="C1"]').click());
  await pv.waitForTimeout(150);
  const ld = await pv.evaluate(() => { const a = document.querySelector('.llave[data-llave="C1"]'), l1 = a.querySelector('.pierna[data-pierna="1"]'), l2 = a.querySelector('.pierna[data-pierna="2"]'), d = document.querySelector('#serie-det [data-vivo-serie="C1"]'), t = document.querySelector('#serie-det [data-avanza-t]');
    return { ida: !!l1.querySelector('.tablero--real.tablero--vivo') && Array.from(l1.querySelectorAll('.tablero b')).map(b => b.textContent).join('-') === '0-1' && /En juego/.test(l1.textContent) && /Ida/.test(l1.textContent), vuelta: !l2.querySelector('.tablero--real') && !!l2.querySelector('.x12'),
      detalle: !!d && !d.hidden && /Al momento/.test(d.textContent) && /87%/.test(d.textContent), antes: t ? t.textContent : '' }; });
  revisa(ld.ida && ld.vuelta, 'en vivo: en la tarjeta de la serie la pierna que se juega muestra su marcador real («En juego») y la otra sigue como pronóstico', JSON.stringify(ld));
  revisa(ld.detalle && /antes del partido/.test(ld.antes), 'en vivo: el detalle de la serie también muestra el global y el avance al momento, y rotula el previo', JSON.stringify(ld));
  const otra = copia(lig); otra.generado_utc = '2026-11-21T23:45:30Z';
  otra.series[0].mejor = { equipo: C2.mejor, siembra: 1 }; otra.series[0].peor = { equipo: C2.peor, siembra: 8 };
  await pv.evaluate(d => window.__vivo(d, false), otra);
  await pv.waitForTimeout(200);
  const lo = await pv.evaluate(() => { const a = document.querySelector('.llave[data-llave="C1"]'); return { oculto: Array.from(document.querySelectorAll('[data-vivo-serie="C1"]')).every(e => e.hidden), ida: !a.querySelector('.pierna[data-pierna="1"] .tablero--real'), clase: a.classList.contains('llave--vivo'), mini: !!document.querySelector('.mc[data-ver-llave="C1"] .mc__vivo') }; });
  revisa(lo.oculto && lo.ida && !lo.clase && !lo.mini, 'en vivo: una serie del documento con la misma llave pero otros equipos no se pinta sobre la tarjeta', JSON.stringify(lo));
  lig.generado_utc = '2026-11-21T23:45:40Z';
  await pv.evaluate(d => window.__vivo(d, false), lig);
  await pv.waitForTimeout(150);

  /* documentos corruptos o incompletos: nada se rompe */
  const raros = [{}, { partidos: null, tabla: null, proyeccion: null }, { version: 1, estado: 'en_juego', generado_utc: 'ayer', partidos: [null, 7, { id: 1, local: null }], tabla: [null, 'x'], series: 'x', ultimo_evento: 5 },
    { generado_utc: '2026-11-21T23:46:00Z', estado: null, partidos: [{ id: 5, local: 'Pachuca', visitante: 'Toluca', estado: 'en_juego', minuto: null, periodo: null, reloj_utc: null, gl: null, gv: null, rojas_l: null, eventos: [null, {}, { min: null, tipo: 'cosa' }], previo: null, vivo: {}, serie: {} },
      { id: idJ, local: 'Pachuca', visitante: 'Toluca', estado: 'descanso', gl: 2, gv: 1, eventos: null, previo: { p_local: null }, vivo: { p_local: 0.8, p_empate: null }, serie: { llave: 'C9', mejor: null } },
      { id: idF, local: 'Puebla', visitante: 'Atlético San Luis', estado: 'final', gl: 2, gv: 0, previo: null, vivo: null }],
      tabla: [{ equipo: 'Pachuca', pos: null, PTS: null, cambio: null }, { equipo: 'Equipo Nuevo', pos: 2, cambio: -3, en_juego: true }], proyeccion: { clasifica: [null, { equipo: 'Pachuca', p: null }, { equipo: 'León', p: 0.4, delta: null }], campeon: null }, series: [null, { llave: 'C1' }, { llave: 'S1', mejor: { equipo: 'Cruz Azul' }, peor: null, global: { mejor: 1, peor: null } }], ultimo_evento: { utc: null, texto: null }, siguiente: null },
    null, [1, 2], 'texto'];
  for (const r of raros) { await pv.evaluate(d => window.__vivo(d, false), r); await pv.waitForTimeout(120); }
  await pv.clock.fastForward(3000);
  const tr = await estado();
  const malaR = palabrasMalas(await textoVisible(pv));
  revisa(errV.length === 0 && tr.respaldos === 0 && !malaR, 'en vivo: documentos corruptos ({}, null, campos raros) no rompen nada ni dejan errores', errV.slice(0, 3).join(' || ') + ' ' + tr.respaldos + ' ' + (malaR || ''));
  revisa(!tr.franja && !tr.seccion && tr.conexion.some(t => /sin partidos en juego/.test(t)), 'en vivo: sin documento válido se retira la franja y lo dice', JSON.stringify([tr.franja, tr.seccion, tr.conexion]));
  /* día sin partidos, tal como lo escribe el motor: tabla y proyección, pero nada «al momento» */
  await pv.evaluate(d => window.__vivo(d, false), { version: 1, generado_utc: '2026-11-21T23:47:00Z', dia: '2026-11-21', estado: 'sin_partidos', partidos: [], tabla: EJEMPLO.tabla, tabla_nota: 'Tabla general: hoy no hay partidos.', proyeccion: EJEMPLO.proyeccion, series: [], ultimo_evento: null, siguiente: EJEMPLO.siguiente });
  await pv.waitForTimeout(150);
  const sinp = await estado();
  revisa(!sinp.franja && !sinp.seccion && !sinp.navVivo && sinp.conexion.some(t => /^Conexión en vivo lista · sin partidos en juego/.test(t)), 'en vivo: en un día sin partidos no aparece nada «al momento»', JSON.stringify([sinp.franja, sinp.seccion, sinp.navVivo, sinp.conexion]));
  lig.generado_utc = '2026-11-21T23:48:00Z';
  await pv.evaluate(d => window.__vivo(d, false), lig);
  await pv.waitForTimeout(200);
  const vuelve = await estado();
  revisa(vuelve.franja && vuelve.marcador === '2-1' && vuelve.subs === 1, 'en vivo: al volver un documento válido todo se repone');
  const desbV = await desbordes(pv);
  revisa(desbV.sw <= desbV.ancho + 1 && desbV.malos.length === 0, 'en vivo: sin desplazamiento horizontal ni elementos fuera', desbV.sw + ' ' + desbV.malos.join(' | '));
  await pv.close();

  /* copia guardada (fromCache) y luego la definitiva; base que nunca contesta; base nula */
  const errC = [];
  const pc = await abrir(ctx, errC);
  await pc.clock.install({ time: new Date(AHORA_EJEMPLO) });
  await pc.addInitScript(guionClaude('mudo'));
  await pc.goto(URL_DOC, { waitUntil: 'load' });
  await pc.waitForTimeout(500);
  const c0 = await pc.evaluate(() => document.querySelector('.js-conexion').textContent);
  await pc.clock.fastForward(11000);
  await pc.waitForTimeout(100);
  const c1 = await pc.evaluate(() => ({ t: document.querySelector('.js-conexion').textContent, tarjetas: document.querySelectorAll('.partido').length }));
  revisa(/^Conectando en vivo/.test(c0) && /^Sin conexión en vivo por ahora: datos del \d+ \w+, \d\d:\d\d h \(centro de México\)/.test(c1.t) && c1.tarjetas > 0 && errC.length === 0, 'en vivo: «conectando» tiene límite de 10 s y la página sigue completa', JSON.stringify([c0, c1]) + errC.join('|'));
  await pc.close();
  const pn = await abrir(ctx, errC);
  await pn.addInitScript(guionClaude('nulo'));
  await pn.goto(URL_DOC, { waitUntil: 'load' });
  await pn.waitForTimeout(600);
  const cn = await pn.evaluate(() => ({ t: document.querySelector('.js-conexion').textContent, franja: !document.getElementById('franja').hidden }));
  revisa(/^Sin conexión en vivo: datos (de las|del \d+ \w+,) \d\d:\d\d/.test(cn.t) && !cn.franja && errC.length === 0, 'en vivo: si use("db") da null la página funciona igual y lo dice', JSON.stringify(cn));
  await pn.close();

  /* «vivo» incrustado (sin base): se usa si es reciente, con el minuto detenido, y se ignora si es viejo */
  const urlVivo = variante('vivo', d => { d.vivo = copia(EJEMPLO); });
  const pi = await abrir(ctx, errC);
  await pi.clock.install({ time: new Date(AHORA_EJEMPLO) });
  await pi.goto(urlVivo, { waitUntil: 'load' });
  await pi.waitForTimeout(600);
  await pi.clock.fastForward(180000);
  await pi.waitForTimeout(100);
  const inc = await pi.evaluate(() => ({ franja: !document.getElementById('franja').hidden, min: (document.querySelector('.fr__min') || {}).textContent, t: document.querySelector('.js-conexion').textContent, ejemplo: /ejemplo/i.test(document.getElementById('vivo').textContent) }));
  revisa(inc.franja && inc.min === "57'" && /^Sin conexión en vivo: datos de las 17:41/.test(inc.t) && inc.ejemplo, 'vivo incrustado sin base: se muestra, dice de qué hora es y no avanza el reloj', JSON.stringify(inc));
  await pi.close();
  const ctxN = await navegador.newContext(Object.assign({ ignoreHTTPSErrors: true, locale: 'es-MX' }, opciones)); /* reloj real: el ejemplo es de otro día */
  const pj = await abrir(ctxN, errC);
  await pj.goto(urlVivo, { waitUntil: 'load' });
  await pj.waitForTimeout(500);
  const viejo = await pj.evaluate(() => ({ franja: !document.getElementById('franja').hidden, seccion: !document.getElementById('vivo').hidden }));
  revisa(!viejo.franja && !viejo.seccion && errC.length === 0, 'vivo incrustado de otro día: no se presenta como «al momento»', JSON.stringify(viejo) + errC.join('|'));
  await ctxN.close();

  /* ---------- EN VIVO: flujo cortado, conexión caída, saltos de lectura, prueba, tiempos extra y penales ---------- */
  const errR = [];
  const px = await abrir(ctx, errR);
  await px.clock.install({ time: new Date(AHORA_EJEMPLO) });
  await px.addInitScript(guionClaude('db', null));
  await px.goto(URL_DOC, { waitUntil: 'load' });
  await px.waitForTimeout(700);
  const vista = () => px.evaluate(id => { const q = s => document.querySelector(s), t = e => e ? e.textContent : '', tar = q('#p-' + id + ' [data-pvivo]');
    return { franja: !document.getElementById('franja').hidden, rot: t(q('#franja-rot')), min: t(q('.fr__min')), minTar: t(q('#p-' + id + ' .pvivo__min')), chip: t(q('#p-' + id + ' .pvivo__cab .chip')), chips: tar ? Array.from(tar.querySelectorAll('.pvivo__cab .chip')).map(t) : [], pulsos: document.querySelectorAll('#vivo .chip--vivo, #p-' + id + ' .chip--vivo, .tablero--vivo').length,
      rotulo: t(q('#vivo .rotulo')), con: t(q('.js-conexion')), modo: q('.js-conexion').getAttribute('data-modo'), subs: window.__subs, compara: tar ? tar.querySelectorAll('.compara').length : -1, texto: tar ? tar.textContent : '', marc: t(q('#vm-' + id)), respaldos: document.querySelectorAll('.respaldo').length }; }, idJ);
  /* H06: llega el primer documento mientras alguien lee la tabla general: lo que lee no se mueve */
  /* se mide el renglón de la tabla que queda al 60% de la pantalla (dentro de la sección también aparece un botón «ver la tabla al momento») */
  const salto = async doc => { const a = await px.evaluate(() => { const e = document.elementFromPoint(Math.floor(window.innerWidth / 2), Math.floor(window.innerHeight * 0.6)); window.__leo = e; return { top: Math.round(e.getBoundingClientRect().top), enTabla: !!e.closest('#b-tabla'), y: window.pageYOffset }; });
    await px.evaluate(d => window.__vivo(d, false), doc); await px.waitForTimeout(250);
    return { antes: a.top, enTabla: a.enTabla, despues: await px.evaluate(() => Math.round(window.__leo.getBoundingClientRect().top)), dy: (await px.evaluate(() => window.pageYOffset)) - a.y }; };
  await px.evaluate(() => { const e = document.getElementById('b-tabla'); window.scrollTo(0, window.pageYOffset + e.getBoundingClientRect().top - 150); });
  await px.waitForTimeout(1200);                                  /* que termine la animación de entrada de la sección */
  const s1 = await salto(EJEMPLO);
  const masGoles = copia(EJEMPLO); masGoles.generado_utc = '2026-11-21T23:41:25Z';
  masGoles.partidos[0].eventos = masGoles.partidos[0].eventos.concat([4, 5, 6, 7].map(k => ({ min: 50 + k, anadido: null, tipo: 'gol', equipo: 'Pachuca', jugador: 'Jugador ' + k, marcador: k + '-1' })));
  masGoles.partidos[2].estado = 'en_juego'; Object.assign(masGoles.partidos[2], { periodo: 1, minuto: 3, gl: 0, gv: 0, reloj_utc: '2026-11-21T23:41:20Z', vivo: masGoles.partidos[0].vivo });
  const s2 = await salto(masGoles);
  revisa(s1.enTabla && Math.abs(s1.despues - s1.antes) <= 2 && s1.dy > 400 && Math.abs(s2.despues - s2.antes) <= 2 && s2.dy > 100, 'en vivo: cuando «Al momento» aparece o crece arriba, lo que se está leyendo no se mueve', JSON.stringify([s1, s2]));
  await px.evaluate(() => window.scrollTo(0, 0));
  await px.evaluate(d => window.__vivo(d, false), Object.assign(copia(EJEMPLO), { generado_utc: '2026-11-21T23:41:28Z' }));
  await px.waitForTimeout(200);
  /* H05: error terminal del oyente → el reloj no retrocede y la página vuelve a suscribirse sola */
  await px.clock.fastForward(120000);
  await px.waitForTimeout(100);
  const k0 = await vista();
  await px.evaluate(() => window.__err('unavailable'));
  await px.waitForTimeout(100);
  const k1 = await vista();
  await px.clock.fastForward(6000);
  await px.waitForTimeout(400);
  const k2 = await vista();
  revisa(k0.min === "59'" && k1.min === "59'" && /^Sin conexión en vivo por ahora/.test(k1.con) && k1.subs === 1, 'en vivo: al caer la conexión el minuto no retrocede y lo dice', JSON.stringify([k0.min, k1.min, k1.con, k1.subs]));
  revisa(k2.subs === 2 && k2.modo === 'vivo' && /^En vivo · actualizado/.test(k2.con) && k2.franja, 'en vivo: tras un error del oyente la página abre otra suscripción (una sola) y se repone', JSON.stringify([k2.subs, k2.modo, k2.con]));
  /* H02: se corta el flujo → pasado vence_utc deja de decir «en vivo» */
  await px.clock.fastForward(20 * 60000);
  await px.waitForTimeout(100);
  const a1 = await vista();
  await px.clock.fastForward(16 * 60000);
  await px.waitForTimeout(150);
  const a2 = await vista();
  revisa(a1.franja && a1.pulsos > 0 && a1.rotulo === 'Ejemplo', 'en vivo: dentro del plazo del motor (vence_utc) sigue en vivo', JSON.stringify([a1.franja, a1.pulsos, a1.rotulo, a1.min]));
  revisa(!a2.franja && a2.pulsos === 0 && /^Sin actualizar desde las 17:41 h$/.test(a2.chip) && a2.minTar === "57'" && a2.rotulo === 'Hoy' && /^Datos en vivo atrasados: última actualización a las 17:41 h \(centro de México\)/.test(a2.con) && a2.modo === 'espera',
    'en vivo: si el flujo se corta, al vencer el documento se retira la franja, se detiene el reloj y dice «Sin actualizar desde las HH:MM»', JSON.stringify(a2));
  /* H07: un documento de prueba se rotula */
  const ahoraX = await px.evaluate(() => new Date().toISOString());
  const fresco = (extra, fn) => { const d = copia(EJEMPLO); delete d.ejemplo; d.generado_utc = ahoraX; d.vence_utc = new Date(Date.parse(ahoraX) + 37 * 60000).toISOString(); d.partidos[0].reloj_utc = ahoraX; Object.assign(d, extra || {}); if (fn) fn(d); return d; };
  await px.evaluate(d => window.__vivo(d, false), fresco({ prueba: true }));
  await px.waitForTimeout(200);
  const prb = await vista();
  revisa(prb.franja && prb.rot === 'Prueba' && prb.rotulo === 'Prueba' && prb.chips.indexOf('Prueba') >= 0 && /datos de prueba$/.test(prb.con), 'en vivo: un documento con «prueba: true» se rotula como prueba (franja, sección, tarjeta y conexión)', JSON.stringify([prb.rot, prb.rotulo, prb.chips, prb.con]));
  /* H08: final con tiempos extra y penales */
  const F = { llave: 'F', fase: 'final', mejor: 'Pachuca', peor: 'Toluca', global_mejor: 2, global_peor: 2, p_avanza_mejor: 0.5, p_avanza_peor: 0.5, decidida: false, ganador: null };
  await px.evaluate(d => window.__vivo(d, false), fresco({ generado_utc: new Date(Date.parse(ahoraX) + 1000).toISOString() }, d => Object.assign(d.partidos[0], { periodo: 5, minuto: 120, anadido: null, gl: 2, gv: 2, gl90: 1, gv90: 1, penales: { l: 1, v: 2 }, vivo: { p_local: 0, p_empate: 1, p_visitante: 0, goles_restantes_l: 0, goles_restantes_v: 0, marcador_final: { gl: 1, gv: 1, prob: 1 } }, serie: F })));
  await px.waitForTimeout(200);
  await px.clock.fastForward(6 * 60000);
  await px.waitForTimeout(100);
  const pnl = await vista();
  revisa(pnl.min === 'Penales' && pnl.minTar === 'Penales' && pnl.compara === 0 && /A los 90 minutos: 1-1/.test(pnl.texto) && /Penales: 1-2/.test(pnl.texto) && /Campeón: \w+ 50% · \w+ 50%/.test(pnl.texto) && !/100%/.test(pnl.marc),
    'en vivo: en penales no corre el reloj ni se muestra el 1X2 de los 90 minutos; dice el marcador a 90\' y el de la tanda', JSON.stringify([pnl.min, pnl.minTar, pnl.compara, pnl.texto.slice(-260), pnl.marc]));
  await px.evaluate(d => window.__vivo(d, false), fresco({ generado_utc: new Date(Date.parse(ahoraX) + 8 * 60000).toISOString(), estado: 'terminado_hoy' }, d => { Object.assign(d.partidos[0], { estado: 'final', periodo: 5, minuto: 120, anadido: null, gl: 2, gv: 2, gl90: 1, gv90: 1, penales: { l: 3, v: 4 }, vivo: null, previo: Object.assign({}, d.partidos[0].previo, { marcador: { gl: 1, gv: 1 } }), serie: Object.assign({}, F, { p_avanza_mejor: 0, p_avanza_peor: 1, decidida: true, ganador: 'Toluca' }) }); d.partidos[1].estado = 'final'; }));
  await px.waitForTimeout(200);
  const fpn = await vista();
  revisa(/Penales: 3-4/.test(fpn.texto) && /Campeón: Toluca/.test(fpn.texto) && /Marcador exacto/.test(fpn.texto) && /Penales: 3-4/.test(fpn.marc) && !fpn.franja,
    'en vivo: final decidida en penales: tanda, campeón y el pronóstico calificado con el marcador a 90 minutos', JSON.stringify([fpn.texto.slice(-300), fpn.marc]));
  const malaX = palabrasMalas(await textoVisible(px));
  revisa(errR.length === 0 && fpn.respaldos === 0 && !malaX, 'en vivo (robustez): sin errores de consola, bloques de respaldo ni «undefined»', errR.slice(0, 3).join(' || ') + ' ' + fpn.respaldos + ' ' + (malaX || ''));
  /* error que no se arregla reintentando: se queda sin conexión y no vuelve a suscribirse */
  await px.evaluate(() => window.__err('revoked'));
  await px.clock.fastForward(70000);
  await px.waitForTimeout(200);
  const rvk = await vista();
  revisa(rvk.subs === 2 && /^Sin conexión en vivo: datos/.test(rvk.con), 'en vivo: con un error definitivo (acceso revocado) no reintenta y lo dice', JSON.stringify([rvk.subs, rvk.con]));
  /* aviso: no intercepta toques y no pasa de dos renglones */
  const avs = await px.evaluate(() => { const a = document.getElementById('aviso'); a.textContent = 'Gol de Atlético San Luis de penal (90+12): un jugador con un nombre muy largo que no cabe. Atlético San Luis 3-3 Mazatlán, y más texto para forzar varios renglones en el aviso'; a.hidden = false; const cs = getComputedStyle(a), r = a.getBoundingClientRect(); a.hidden = true; return { pe: cs.pointerEvents, alto: Math.round(r.height), renglon: parseFloat(cs.lineHeight) }; });
  revisa(avs.pe === 'none' && avs.alto <= avs.renglon * 2 + 24, 'en vivo: el aviso no intercepta toques y ocupa como mucho dos renglones', JSON.stringify(avs));
  await px.close();

  /* ---------- variante: liguilla en curso y opcionales en null ---------- */
  const errL = [];
  const pl = await abrir(ctx, errL);
  await pl.goto(variante('liguilla', conLiguillaEnCurso), { waitUntil: 'load' });
  await pl.waitForTimeout(500);
  const sinElegir = await pl.evaluate(() => document.querySelectorAll('#serie-det .leg').length + document.querySelectorAll('.llave--sel').length);
  await pl.evaluate(() => document.querySelector('.serie-sel [data-serie="C1"]').click());
  await pl.waitForTimeout(100);
  const v = await pl.evaluate(() => {
    const q = s => document.querySelector(s), c1 = q('.llave[data-llave="C1"]'), c2 = q('.llave[data-llave="C2"]'), c3 = q('.llave[data-llave="C3"]'), s1 = q('.llave[data-llave="S1"]');
    const piernas = Array.from(c1.querySelectorAll('.pierna'));
    return { llaves: document.querySelectorAll('#cuadro .llave').length, tarjetas: document.querySelectorAll('.partido').length, respaldos: document.querySelectorAll('.respaldo').length,
      idaReal: !!piernas[0].querySelector('.tablero--real') && /Resultado/.test(piernas[0].textContent) && Array.from(piernas[0].querySelectorAll('.tablero b')).map(b => b.textContent).join('-') === '1-0',
      vueltaPron: !piernas[1].querySelector('.tablero--real') && !!piernas[1].querySelector('.x12') && /28 nov/.test(piernas[1].textContent),
      chips: [c1, c2, c3, s1].map(l => (l.querySelector('.llave__id .chip') || {}).textContent), globalIda: /Global hasta hoy/.test(c1.textContent) && !!c1.querySelector('.llave__global .tablero--real') && !/Cierre probable|Global probable/.test(c1.textContent) && !c3.querySelector('.llave__global'), leyenda: !!q('.leyenda-m'),
      mini: (() => { const n1 = q('.mc[data-ver-llave="C1"]'), n2 = q('.mc[data-ver-llave="C2"]'); return [n1.querySelectorAll('.mc__leg.real').length, /%/.test(n1.textContent), n2.querySelectorAll('.mc__leg.real').length, !!n2.querySelector('.mc__eq.fuera'), /%/.test(n2.textContent), Array.from(n2.querySelectorAll('.mc__eq i')).map(x => x.textContent).join('-')]; })(),
      avanza: /Avanza/.test(c2.textContent) && !!c2.querySelector('.llave__eq.fuera') && /Global final/.test(c2.textContent), estado: q('.cuadro-estado').textContent,
      sel: (q('.llave--sel') || { getAttribute: () => '' }).getAttribute('data-llave'), legReal: document.querySelectorAll('#serie-det .leg--real').length, legs: document.querySelectorAll('#serie-det .leg').length,
      sw: document.documentElement.scrollWidth, ancho: window.innerWidth, grupos: Array.from(document.querySelectorAll('#b-partidos .grupo > h3')).map(h => h.textContent) };
  });
  revisa(v.llaves === 7 && v.idaReal && v.vueltaPron && v.globalIda && v.leyenda, 'liguilla en curso: la ida jugada sale como resultado real resaltado, con el global real, y la vuelta como pronóstico con su fecha', JSON.stringify(v));
  revisa(JSON.stringify(v.mini) === JSON.stringify([1, true, 2, true, false, '2-1']), 'liguilla en curso: el mini-cuadro pone en blanco lo jugado y, en la serie terminada, el global real con el eliminado atenuado', JSON.stringify(v.mini));
  revisa(v.chips[0] === 'En curso' && v.chips[1] === 'Terminada' && v.chips[2] === 'Definida' && v.chips[3] === 'Proyectada' && v.avanza && /en curso/i.test(v.estado), 'liguilla en curso: estados por serie (en curso, terminada con quien avanza, definida, proyectada)', JSON.stringify(v.chips));
  revisa(sinElegir === 0 && v.sel === 'C1' && v.legs === 2 && v.legReal === 1, 'liguilla en curso: el detalle de la serie en curso trae la ida real y la vuelta en pronóstico', JSON.stringify([sinElegir, v.sel, v.legs, v.legReal]));
  revisa(v.tarjetas === 10 && v.respaldos === 0 && errL.length === 0, 'variante: datos en null no rompen nada', JSON.stringify([v.tarjetas, v.respaldos]) + ' ' + errL.slice(0, 3).join(' || '));
  revisa(v.grupos.includes('Cuartos de final, ida'), 'variante: los partidos de liguilla forman su grupo', v.grupos.join(', '));
  for (const k of ['C2', 'C4', 'S2', 'F']) { await pl.evaluate(k => document.querySelector('.serie-sel [data-serie="' + k + '"]').click(), k); await pl.waitForTimeout(60); }
  const desbL = await desbordes(pl);
  revisa(desbL.sw <= desbL.ancho + 1 && desbL.malos.length === 0, 'variante: sin desplazamiento horizontal', desbL.sw + ' ' + desbL.malos.join(' | '));
  const malaV = palabrasMalas(await textoVisible(pl));
  revisa(!malaV && errL.length === 0 && await pl.evaluate(() => document.querySelectorAll('.respaldo').length) === 0, 'variante: sin "undefined", "NaN" ni "null" (también al recorrer el detalle de cada serie)', (malaV || '') + errL.slice(0, 2).join('|'));
  await pl.evaluate(() => document.querySelector('.serie-sel [data-serie="C1"]').click());
  await capElDe(pl)('10-liguilla-en-curso', '#b-llaves', movil ? 1500 : 1000);
  await capElDe(pl)('10b-detalle-en-curso', '#serie-det', 1500);
  await pl.close();

  /* sin liguilla.torneo: aviso en lugar del cuadro */
  const ps = await abrir(ctx, errL);
  await ps.goto(variante('sintorneo', d => { d.liguilla.torneo = null; d.liguilla.cuadro_proyectado = null; }), { waitUntil: 'load' });
  await ps.waitForTimeout(400);
  const st = await ps.evaluate(() => ({ vacio: !!document.querySelector('#b-llaves .vacio'), respaldos: document.querySelectorAll('.respaldo').length, tarjetas: document.querySelectorAll('.partido').length }));
  revisa(st.vacio && st.respaldos === 0 && st.tarjetas > 0 && errL.length === 0, 'sin liguilla.torneo: estado vacío en lugar del cuadro, sin errores', JSON.stringify(st) + errL.slice(0, 2).join('|'));
  await ps.close();
  await ctx.close();

  /* ---------- movimiento reducido ---------- */
  const ctxR = await navegador.newContext(Object.assign({ ignoreHTTPSErrors: true }, opciones, { reducedMotion: 'reduce' }));
  const pr = await ctxR.newPage();
  await pr.addInitScript(() => { window.__raf = 0; const o = window.requestAnimationFrame; window.requestAnimationFrame = function (f) { window.__raf++; return o.call(window, f); }; });
  await pr.goto(URL_DOC, { waitUntil: 'load' });
  await pr.waitForTimeout(900);
  const red = await pr.evaluate(() => { const im = document.querySelector('#portada .fondo img'), cv = document.getElementById('confeti'), px = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data; let n = 0; for (let i = 3; i < px.length; i += 4) if (px[i] > 20) n++;
    return { anim: im.getAnimations ? im.getAnimations().length : 0, raf: window.__raf, confeti: n, animadas: document.querySelectorAll('.entra').length, videos: Array.from(document.querySelectorAll('video')).filter(v => !v.paused).length }; });
  revisa(red.anim === 0 && red.raf === 0 && red.confeti > 40 && red.animadas === 0 && red.videos === 0, 'movimiento reducido: foto quieta, confeti fijo, sin animaciones ni video', JSON.stringify(red));
  await ctxR.close();
}

(async () => {
  /* --vivo (opción de prueba) incrusta el documento en vivo sólo en documento.html; después se construye la página normal */
  const indice = path.join(WEB, 'index.html'), huella = f => fs.existsSync(f) ? fs.statSync(f).mtimeMs : 0;
  const antesIndice = huella(indice);
  execFileSync('python3', [path.join(WEB, 'construir.py'), '--vivo', path.join(WEB, '..', 'salidas', 'vivo_ejemplo.json')], { stdio: 'pipe' });
  const conVivo = fs.readFileSync(path.join(WEB, 'documento.html'), 'utf8'), intacto = huella(indice) === antesIndice;
  execFileSync('python3', [path.join(WEB, 'construir.py'), '--documento', '--salida', WEB], { stdio: 'inherit' });
  const frag = fs.readFileSync(indice, 'utf8');
  const antes = frag.split('<script type="application/json"')[0];
  const guion = frag.split('</script>').slice(-2)[0];
  console.log('== archivo ==');
  revisa(!/<!doctype|<html[\s>]|<head[\s>]|<body[\s>]/i.test(antes), 'index.html es un fragmento (sin doctype, html, head ni body)');
  revisa(/^<title>Cerebro Liga MX<\/title>\s*<meta name="claude:viewport-fit-sides" content="cover">/.test(frag), 'empieza con <title> y la meta de la plataforma');
  revisa(!/<script[^>]+src=|<iframe|location\.hash|pushState|\balert\(|\bconfirm\(|\bprompt\(|localStorage|location\.reload/.test(antes + guion), 'sin scripts externos, iframes, hash, alert, localStorage ni recargas');
  revisa(!/<link[^>]+href="(?!https:\/\/fonts\.googleapis\.com\/)/.test(antes) && !/(src|poster)="https?:/.test(antes), 'hojas de estilo sólo de Google Fonts; imágenes y videos sólo propios');
  const css = /<style>([\s\S]*?)<\/style>/.exec(frag)[1], raiz = /:root\{[\s\S]*?\n\}/.exec(css)[0];
  const literales = css.replace(raiz, '').match(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/g);
  revisa(!literales, 'ningún color literal fuera de los tokens de :root', (literales || []).slice(0, 5).join(' '));
  revisa(/color-scheme:dark/.test(raiz) && /body\{[^}]*background:var\(--noche\)/.test(css) && /max\(16px, env\(safe-area-inset-left/.test(raiz) && /max\(16px, env\(safe-area-inset-right/.test(raiz), 'un solo tema oscuro, fondo explícito y canal lateral con env(safe-area-inset-*)');
  revisa(/\.use\('db'\)/.test(guion) && /\.doc\('vivo\/actual'\)/.test(guion) && (guion.match(/onSnapshot\(/g) || []).length === 1 && !/window\.claude\.(db|room|artifact)/.test(guion), 'usa la capacidad con claude.use("db") y una sola llamada a onSnapshot');
  const caps = JSON.parse(fs.readFileSync(path.join(WEB, 'capacidades.json'), 'utf8'));
  revisa(caps.db && Array.isArray(caps.db.rules), 'capacidades.json declara la capacidad "db"', JSON.stringify(caps));
  const datosDe = h => JSON.parse(/<script type="application\/json" id="datos">([\s\S]*?)<\/script>/.exec(h)[1]);
  const vivoPrueba = datosDe(conVivo).vivo, vivoNormal = datosDe(frag).vivo, vivoActual = JSON.parse(fs.readFileSync(path.join(WEB, '..', 'salidas', 'actual.json'), 'utf8')).vivo;
  revisa(vivoPrueba && vivoPrueba.ejemplo === true && intacto, 'construir.py --vivo incrusta ese documento en documento.html y no toca index.html');
  revisa(JSON.stringify(vivoNormal) === JSON.stringify(vivoActual) && !(vivoNormal && vivoNormal.ejemplo), 'sin la opción, index.html incrusta actual.json → vivo sólo si existe (' + (vivoActual ? 'hoy existe: ' + vivoActual.estado : 'hoy no existe') + ')');
  const usados = JSON.parse(fs.readFileSync(path.join(WEB, 'archivos_publicados.json'), 'utf8'));
  const enPagina = Array.from(new Set((frag.match(/(?:img|video)\/[\w./-]+\.(?:jpg|jpeg|png|webp|svg|mp4)/g) || [])));
  revisa(usados.length > 0 && usados.every(r => fs.existsSync(path.join(WEB, r))) && enPagina.every(r => usados.includes(r)), 'archivos_publicados.json: los ' + usados.length + ' archivos existen y cubren todo lo que la página usa', enPagina.filter(r => !usados.includes(r)).slice(0, 4).join(', '));

  const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
  const navegador = await pw[motor].launch(proxy ? { proxy: { server: proxy } } : {});
  try {
    await correr(navegador, 'iphone', pw.devices['iPhone 13']);
    await correr(navegador, 'escritorio', { viewport: { width: 1440, height: 900 } });
  } finally {
    await navegador.close();
    temporales.forEach(f => { try { fs.unlinkSync(f); } catch (e) { /* ya no estaba */ } });
  }
  console.log('\n' + (fallas.length ? 'FALLARON ' + fallas.length + ' de ' + revisados + ':\n - ' + fallas.join('\n - ') : 'TODO BIEN: ' + revisados + ' revisiones en ' + motor));
  process.exit(fallas.length ? 1 : 0);
})().catch(e => { console.error(e); temporales.forEach(f => { try { fs.unlinkSync(f); } catch (x) { /* nada */ } }); process.exit(1); });
