#!/usr/bin/env node
/* Pruebas de la página de Cerebro Liga MX con Playwright.

   Uso (desde cualquier carpeta):
     PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node web/pruebas/prueba.js chromium [--capturas]
     PLAYWRIGHT_BROWSERS_PATH=<carpeta con webkit> node web/pruebas/prueba.js webkit [--capturas]

   Arma TRES documentos y los abre con file:// desde web/ en iPhone 13 y en escritorio 1440x900:
   - el de HOY (construir.py --documento --salida web/ → documento.html, con salidas/actual.json): se revisa lo que
     toque según SU estado (partidos pendientes o no, piernas de liguilla sin día ni hora, cuadro proyectado / definido
     / en curso / terminado, fase regular terminada o no, combinada o no). Las expectativas salen de los datos
     incrustados, nunca de la fecha;
   - uno FIJO con partidos pendientes (pruebas/datos/actual_20261120T0722Z.json: 9 pendientes, cuadro proyectado),
     con el reloj del navegador en el 20-nov (AHORA_FIJO): ahí corren SIEMPRE las revisiones de tarjetas de partido,
     pestañas de combinada, cuenta regresiva, cuadro, en vivo y sus variantes;
   - uno FIJO sin partidos pendientes y con el cuadro definido (pruebas/datos/actual_20261123T0353Z.json, la noche
     del 22-nov: fase regular terminada, cuartos sin día ni hora), con el reloj en AHORA_DEFINIDO: anuncio de la
     liguilla bajo la portada, las 8 piernas de cuartos como tarjetas compactas, series «Definida», sin secciones
     vacías; y sus variantes (datos viejos sin el campo «definida», idas ya en el calendario, semifinales definidas,
     liguilla terminada).
   Los dos fijos se arman con «construir.py --datos … --solo-documento», que no toca index.html. Revisa:
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
     opcionales en null, «vivo» incrustado, movimiento reducido;
   - según el estado de los datos (revisaSegunDatos: los de hoy, la copia «definido» y sus variantes): bajo la portada
     el próximo partido con cuenta regresiva o el anuncio de la ronda que sigue (cruces, ventana de fechas, botón al
     cuadro); «Próximos partidos» con una tarjeta por pendiente y las piernas de liguilla sin día ni hora como
     tarjetas compactas (contenido, orden, nombres sin partir, pie alineado, botón al detalle de la serie) o retirada
     si no hay nada; combinada de la jornada o sección retirada; ninguna sección visible vacía; menú y numeración;
     etiqueta de cada serie (Terminada / En curso / Definida / Proyectada); textos de la fase regular terminada;
     conexión sin window.claude («vivo» incrustado de hoy o corte);
   - desempeño sellado, modelo contra mercado: con los datos de hoy (lo que diga desempeno.contra_mercado) y con
     variantes de 3, 1 y 40 partidos comparados, sin ningún sello con momios, documento viejo sin el campo y
     mercado con basura; tarjeta de cada resultado con y sin mercado en su sello.
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
const DATOS = path.join(__dirname, 'datos');
const SUF = '_' + process.pid;                                     /* dos corridas a la vez no se pisan los temporales */
const DOC_REAL = path.join(WEB, 'documento.html');                 /* los datos de hoy (salidas/actual.json) */
const DOC_FIJO = path.join(WEB, '_variante' + SUF + '_pendientes.html');  /* copia fija: 9 partidos pendientes, cuadro proyectado */
const DOC_DEFINIDO = path.join(WEB, '_variante' + SUF + '_definido.html'); /* copia fija: 0 pendientes, cuadro definido */
const DATOS_FIJO = path.join(DATOS, 'actual_20261120T0722Z.json'), DATOS_DEFINIDO = path.join(DATOS, 'actual_20261123T0353Z.json');
const URL_REAL = 'file://' + DOC_REAL, URL_DOC = 'file://' + DOC_FIJO, URL_DEFINIDO = 'file://' + DOC_DEFINIDO;
const AHORA_FIJO = '2026-11-20T08:00:00Z';                        /* 38 min después del corte de los datos fijos: sus 9 partidos siguen por jugar */
const AHORA_DEFINIDO = '2026-11-23T04:00:00Z';                    /* 22:00 h del 22-nov en el centro de México: 7 min después del corte; su «vivo» (21:18 h) sigue vigente */
const MES3 = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
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

/* escribe una copia del documento base (por omisión, el fijo con partidos pendientes) con los datos incrustados cambiados por fn(d) */
function variante(nombre, fn, base) {
  const doc = fs.readFileSync(base || DOC_FIJO, 'utf8');
  const re = /(<script type="application\/json" id="datos">)([\s\S]*?)(<\/script>)/;
  const d = JSON.parse(re.exec(doc)[2]);
  fn(d);
  const ruta = path.join(WEB, '_variante' + SUF + '_' + nombre + '.html');
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

/* ---- modelo contra mercado sellado: la página sólo da formato a desempeno.contra_mercado y a pronostico.mercado ---- */
function datosDocumento(ruta) { return JSON.parse(/<script type="application\/json" id="datos">([\s\S]*?)<\/script>/.exec(fs.readFileSync(ruta || DOC_FIJO, 'utf8'))[1]); }
function fechaCortaEsperada(iso) { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso); return +m[3] + ' ' + ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'][+m[2] - 1] + ' ' + m[1]; }
const P_MODELO = { L: 0.5, E: 0.3, V: 0.2 }, P_MERCADO = { L: 0.4, E: 0.3, V: 0.3 };      /* pronósticos INVENTADOS para las variantes */
const PRON_PRUEBA = res => ({ origen: 'sello', sellado_utc: '2026-11-16T08:00:00+00:00', modelo: 'de_prueba', p_local: P_MODELO.L, p_empate: P_MODELO.E, p_visitante: P_MODELO.V, pick: 'L',
  marcador: { gl: 1, gv: 0, prob: 0.12 }, acierto_1x2: res === 'L', marcador_exacto: false, prob_del_resultado: P_MODELO[res], logloss: -Math.log(P_MODELO[res]), mercado: null });
const MERCADO_VACIO = (desde, sellados) => ({ n: 0, n_sin_mercado: 0, n_sellados_con_mercado: sellados, primer_sello_con_mercado_utc: desde ? desde + 'T08:00:00+00:00' : null, desde_local: desde, metodo: 'shin', n_minimo: 30,
  mercado: null, modelo: null, dif_logloss: null, ee_dif_logloss: null, lectura: 'sin_partidos', nota: 'Variante de prueba.' });
/* n partidos comparados, con cifras INVENTADAS como las que exporta Python (redondeadas a 4 decimales). Con 3, el log-loss
   es el del caso a mano de produccion/pruebas/test_sellos_mercado.py (los aciertos son distintos a propósito, para que
   no se puedan confundir); con 1, sin error estándar; con 40, el mercado mejor por más de dos errores estándar. */
function conMercado(d, n) {
  const caso = { 1: { fuera: 0, mo: 1.8971, me: 1.6094, dif: 0.2877, ee: null, eeMo: null, eeMe: null, acMo: 0, acMe: 0, lectura: 'pocos_partidos' },
    3: { fuera: 1, mo: 1.2647, me: 1.304, dif: -0.0393, ee: 0.1639, eeMo: 0.3489, eeMe: 0.2043, acMo: 1, acMe: 2, lectura: 'pocos_partidos' },
    40: { fuera: 1, mo: 1.0412, me: 1.0098, dif: 0.0314, ee: 0.0121, eeMo: 0.0431, eeMe: 0.0402, acMo: 17, acMe: 19, lectura: 'mercado_mejor' } }[n];
  const total = n + caso.fuera;
  d.desempeno.n_calificados = total;
  d.desempeno.acumulado = { n: total, aciertos_1x2: caso.acMo, acierto_1x2: caso.acMo / total, marcadores_exactos: 0, marcador_exacto: 0, logloss: caso.mo, ee_logloss: caso.eeMo, brier: 0.66, rps: 0.23,
    prob_media_del_pick: 0.46, logloss_referencia_tercios: 1.0986, combinadas: {} };
  d.desempeno.contra_mercado = Object.assign(MERCADO_VACIO('2026-11-16', n + 9), { n: n, n_sin_mercado: caso.fuera, lectura: caso.lectura, dif_logloss: caso.dif, ee_dif_logloss: caso.ee,
    mercado: { n: n, logloss: caso.me, ee_logloss: caso.eeMe, brier: 0.7983, rps: 0.2754, aciertos_favorito: caso.acMe, acierto_favorito: caso.acMe / n },
    modelo: { n: n, logloss: caso.mo, ee_logloss: caso.eeMo, brier: 0.7683, rps: 0.2771, aciertos_1x2: caso.acMo, acierto_1x2: caso.acMo / n } });
  const us = d.ultimos_resultados, res = us[0].resultado, ll = -Math.log(P_MODELO[res]), llm = -Math.log(P_MERCADO[res]);
  us[0].pronostico = Object.assign(PRON_PRUEBA(res), { mercado: { proveedor: 'Casa de prueba', ml_local: 2.4, ml_empate: 3.3, ml_visitante: 3.0, margen: 0.053, p_local: P_MERCADO.L, p_empate: P_MERCADO.E, p_visitante: P_MERCADO.V,
    pick: 'L', acierto_1x2: res === 'L', prob_del_resultado: P_MERCADO[res], logloss: llm, dif_logloss: ll - llm } });
  if (us[1]) us[1].pronostico = PRON_PRUEBA(us[1].resultado);                                  /* sello sin momios */
  if (us[2]) us[2].pronostico = Object.assign(PRON_PRUEBA(us[2].resultado), { origen: 'modelo/pred (walk-forward, no sellado)', sellado_utc: null });
}
/* lo que la página dice del mercado sellado: el bloque del desempeño y cada tarjeta de resultado (textContent: igual en los dos motores) */
function leeMercado(pg) {
  return pg.evaluate(() => {
    const t = e => (e ? e.textContent : '').replace(/\s+/g, ' ').trim(), b = document.getElementById('contra-mercado');
    return { hay: !!b, enDesempeno: !!document.querySelector('#b-desempeno .bloque #contra-mercado'), lectura: b ? b.getAttribute('data-lectura') : null, texto: t(b),
      datos: b ? Array.from(b.querySelectorAll('.datos > div')).map(x => [t(x.querySelector('dt')), t(x.querySelector('dd'))]) : [],
      tarjetas: Array.from(document.querySelectorAll('#b-ultima .res')).map(r => ({ marca: r.querySelector('[data-mercado="si"]') ? 'si' : r.querySelector('[data-mercado="no"]') ? 'no' : '', barras: r.querySelectorAll('.x12').length, texto: t(r) })),
      respaldos: document.querySelectorAll('#b-ultima .respaldo, #b-desempeno .respaldo').length, textoDesempeno: t(document.getElementById('b-desempeno')) };
  });
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

/* ---------- lo que la página debe mostrar según el estado de SUS datos (expectativas tomadas de los datos, nunca de la fecha) ---------- */
const COMO_PRONOSTICO = ['lam_l', 'lam_v', 'p_local', 'p_empate', 'p_visitante', 'marcador', 'marcadores'];
function torneoDe(d) { const t = d.liguilla && d.liguilla.torneo; return t && Array.isArray(t.rondas) && t.rondas.length ? t : null; }
/* una serie ya tiene sus dos equipos seguros: el campo «definida»; con datos viejos sin el campo, serie en el calendario o cuartos con la fase regular terminada */
function definidaEsperada(s, t) { return typeof s.definida === 'boolean' ? s.definida : !!s.real || (s.fase === 'cuartos' && ['definido', 'en_curso', 'terminado'].includes(t.estado)); }
/* piernas de liguilla por jugar, entre equipos ya definidos, que no vienen en «pendientes» (la liga no les ha puesto día y hora):
   por ronda, primero las idas y luego las vueltas. Son las tarjetas compactas que «Próximos partidos» debe mostrar */
function piernasEsperadas(d) {
  const t = torneoDe(d), out = []; if (!t) return out;
  const ids = new Set(d.pendientes.map(p => String(p.id))), pares = new Set(d.pendientes.map(p => p.local + '|' + p.visitante));
  for (const r of t.rondas) for (const n of [1, 2]) for (const s of r.series || []) {
    if (!s || !s.llave || s.decidida || !definidaEsperada(s, t)) continue;
    for (const l of s.piernas || []) if (l && (l.pierna === 2 ? 2 : 1) === n && !l.jugado && !(l.id != null && ids.has(String(l.id))) && !pares.has(l.local + '|' + l.visitante)) out.push({ s, l, r, n });
  }
  return out;
}
function chipEsperado(s, t) { /* la pastilla de estado de cada serie en el cuadro (null: no lleva, todo el cuadro es proyectado) */
  if (s.decidida) return 'Terminada';
  if ((s.piernas || []).some(l => l && l.jugado && Number.isFinite(l.gl) && Number.isFinite(l.gv))) return 'En curso';
  const def = definidaEsperada(s, t);
  return def ? 'Definida' : t.estado === 'proyectado' ? null : 'Proyectada';
}
const pctTxt = x => (x * 100).toFixed(1) + '%';
function ventanaTxt(fechas) { /* ['2026-11-25','2026-11-26'] → '25 o 26 nov' (la ventana de una pierna sin fecha) */
  const ps = (fechas || []).map(f => /^(\d{4})-(\d{2})-(\d{2})/.exec(f)).filter(Boolean); if (!ps.length) return '';
  return ps.every(m => m[2] === ps[0][2]) ? ps.map(m => +m[3]).join(' o ') + ' ' + MES3[+ps[0][2] - 1] : ps.map(m => +m[3] + ' ' + MES3[+m[2] - 1]).join(' o ');
}
/* el menú, la barra de escritorio y el número de cada sección siguen a las secciones que sí se muestran */
async function revisaMenu(pg, etq) {
  const men = await pg.evaluate(() => {
    const items = Array.from(document.querySelectorAll('#menu li')).filter(li => !li.hidden).map(li => { const b = li.querySelector('[data-ir]'); return { ir: b.getAttribute('data-ir'), num: (b.querySelector('i') || {}).textContent || '' }; });
    const secciones = Array.from(document.querySelectorAll('main > section[id]')).filter(s => !s.hidden).map(s => s.id);
    const rotulos = {}; document.querySelectorAll('main > section[id] .rotulo').forEach(r => { const m = /^(\d\d)/.exec(r.textContent.trim()); if (m && !r.closest('section').hidden) rotulos[r.closest('section').id] = m[1]; });
    return { items, secciones, rotulos, barra: Array.from(document.querySelectorAll('.barra__nav li')).filter(li => !li.hidden).map(li => li.querySelector('[data-ir]').getAttribute('data-ir')) };
  });
  revisa(men.items.every(i => men.secciones.includes(i.ir)) && men.secciones.every(s => men.items.some(i => i.ir === s)), etq + 'el menú lista exactamente las secciones que existen', JSON.stringify([men.items.map(i => i.ir), men.secciones]));
  const conNumero = men.items.filter(i => i.ir !== 'vivo');        /* «Al momento» va sin número (sólo aparece con partidos de hoy) */
  revisa(conNumero.every((i, k) => i.num === ('0' + k).slice(-2)) && men.items.every(i => i.ir !== 'vivo' || i.num === '') && men.items.every(i => !men.rotulos[i.ir] || men.rotulos[i.ir] === i.num) && men.barra.every(b => men.secciones.includes(b)) &&
    Object.keys(men.rotulos).every(k => men.items.some(i => i.ir === k && i.num === men.rotulos[k])), etq + 'numeración del menú igual a la de las secciones', JSON.stringify([men.items.map(i => i.ir + ':' + i.num), men.rotulos, men.barra]));
  return men;
}
/* sin window.claude: la conexión dice la hora del «vivo» incrustado si tiene partidos de hoy y menos de 12 h (y entonces sale «Al momento»);
   si no, la del corte; con su fecha si no es de hoy en el centro de México */
async function revisaConexion(pg, etq) {
  const c = await pg.evaluate(([MES3]) => {
    const d = JSON.parse(document.getElementById('datos').textContent), v = d.vivo, t = v ? Date.parse(v.generado_utc) : NaN, mx = ms => new Date(ms - 6 * 3600000).toISOString();
    const activo = !!v && Array.isArray(v.partidos) && v.partidos.length > 0 && Number.isFinite(t) && Math.abs(Date.now() - t) <= 12 * 3600000;
    const dia = activo ? mx(t).slice(0, 10) : String(d.meta.corte_local).slice(0, 10), hora = activo ? mx(t).slice(11, 16) : (/(\d{2}:\d{2})/.exec(d.meta.corte_local) || [])[1];
    const f = dia.split('-'), esperado = 'Sin conexión en vivo: datos ' + (dia !== mx(Date.now()).slice(0, 10) ? 'del ' + (+f[2]) + ' ' + MES3[+f[1] - 1] + ', ' + hora + ' h' : 'de las ' + hora + ' h') + ' (centro de México)';
    return { textos: Array.from(document.querySelectorAll('.js-conexion')).map(e => e.textContent), esperado, activo, juego: activo && v.partidos.some(p => p && (p.estado === 'en_juego' || p.estado === 'descanso')),
      seccion: !document.getElementById('vivo').hidden, franja: !document.getElementById('franja').hidden };
  }, [MES3]);
  revisa(c.textos.length > 0 && c.textos.every(x => x === c.esperado) && c.seccion === c.activo && (c.juego || !c.franja),
    etq + 'sin window.claude: la página funciona y lo dice (' + c.esperado + (c.activo ? '; con el «vivo» incrustado de hoy sale «Al momento»' : '') + ')', JSON.stringify(c));
}
/* revisa la página tal como debe verse con SUS datos. extra: { pantalla: revisa la portada en la primera pantalla del celular, ahora: reloj del navegador, foto: nombre de captura } */
async function revisaSegunDatos(ctx, url, etiqueta, movil, opciones, extra) {
  extra = extra || {};
  const etq = etiqueta + ': ', errores = [], pg = await abrir(ctx, errores);
  if (extra.ahora) await pg.clock.install({ time: new Date(extra.ahora) });
  await pg.goto(url, { waitUntil: 'load' });
  await pg.waitForTimeout(700);
  const d = await pg.evaluate(() => JSON.parse(document.getElementById('datos').textContent));
  const t = torneoDe(d), pend = d.pendientes.length, sueltas = piernasEsperadas(d), fin = !!d.proyeccion.regular_completa, cj = d.combinada_jornada;
  const hayComb = !!cj && ['segura', 'equilibrada', 'atrevida'].some(k => cj[k] && (cj[k].picks || []).length > 0);
  console.log('  nota   ' + etiqueta + ': ' + pend + ' partidos pendientes, ' + sueltas.length + ' de liguilla sin día ni hora, cuadro ' + (t ? t.estado : 'ausente') + ', fase regular ' + (fin ? 'terminada' : 'en juego') + (hayComb ? ', con' : ', sin') + ' combinada de la jornada');
  if (movil && extra.pantalla) await primeraPantalla(pg, opciones.viewport, etq + 'portada (celular');

  /* bajo la portada: el próximo partido con su cuenta regresiva, o el anuncio de lo que sigue en la liguilla */
  const sg = await pg.evaluate(() => { const b = document.getElementById('b-sigue'), a = b.querySelector('[data-anuncio]');
    return { reloj: !!b.querySelector('#reloj'), anuncio: a ? a.getAttribute('data-anuncio') : null, texto: b.textContent.replace(/\s+/g, ' ').trim(), titulo: ((b.querySelector('.sigue__duelo') || {}).textContent || '').trim(),
      rotulo: ((b.querySelector('.rotulo') || {}).textContent || '').trim(), cruces: Array.from(b.querySelectorAll('[data-ir-llave]')).map(x => x.getAttribute('data-ir-llave')), boton: !!b.querySelector('[data-ir-cuadro]') }; });
  if (pend) revisa(sg.reloj && !sg.anuncio, etq + 'con partidos pendientes, bajo la portada va el próximo partido con su cuenta regresiva', sg.texto.slice(0, 160));
  else if (t && t.estado !== 'proyectado') {
    const rot = { definido: 'Liguilla definida', en_curso: 'Liguilla en curso', terminado: 'Liguilla terminada' }[t.estado];
    if (sueltas.length) {
      const r = sueltas[0].r, de = sueltas.filter(x => x.r === r), llaves = [...new Set(de.map(x => x.s.llave))], f = r.fechas || {}, fs0 = [].concat(f.ida || [], f.vuelta || []).sort(), m = /^(\d{4})-(\d{2})-(\d{2})/.exec(fs0[0] || '') || [];
      const fechas = !m.length || (sg.texto.includes(' ' + (+m[3]) + ' ') && sg.texto.includes(MESES[+m[2] - 1]));
      revisa(sg.anuncio === t.estado && sg.rotulo === rot && sg.titulo === r.nombre && JSON.stringify(sg.cruces) === JSON.stringify(llaves) && fechas && sg.boton && !sg.reloj &&
        /por confirmar/.test(sg.texto) === de.some(x => !x.l.fecha_local) && !/No hay partidos pendientes/.test(sg.texto),
        etq + 'sin partidos con día y hora, bajo la portada se anuncia lo que sigue («' + rot + ' · ' + r.nombre + '»: sus ' + llaves.length + ' cruces, la ventana de fechas y un botón al cuadro)', JSON.stringify([sg.anuncio, sg.rotulo, sg.titulo, sg.cruces, sg.texto.slice(0, 200)]));
    } else if (t.estado === 'terminado' && t.campeon_decidido) {
      revisa(sg.anuncio === 'terminado' && sg.rotulo === rot && sg.titulo.includes(t.campeon_ruta) && /campeón/i.test(sg.titulo) && sg.boton, etq + 'liguilla terminada: bajo la portada, el campeón y el botón al cuadro', sg.texto);
    } else revisa(!!sg.anuncio && /Todavía no hay partidos con día y hora/.test(sg.texto) && sg.boton, etq + 'sin partidos por jugar definidos: lo dice bajo la portada y lleva al cuadro', sg.texto);
  } else revisa(!sg.anuncio && /No hay partidos pendientes por ahora/.test(sg.texto), etq + 'sin partidos pendientes ni cuadro definido: lo dice bajo la portada', sg.texto);
  if (sg.boton) {
    await pg.click('#b-sigue [data-ir-cuadro]');
    await pg.waitForTimeout(1500);
    const v = await pg.evaluate(() => { const m = document.getElementById('mini-cuadro'), e = m && m.offsetParent ? document.getElementById('b-llaves') : document.getElementById('cuadro'), r = e.getBoundingClientRect(); return { top: Math.round(r.top), alto: window.innerHeight, hash: location.hash, foco: !!(document.activeElement && document.activeElement.closest('#liguilla')) }; });
    revisa(v.top >= 0 && v.top < v.alto * 0.5 && v.hash === '' && v.foco, etq + '«Ver el cuadro» lleva al cuadro de la liguilla (sin location.hash)', JSON.stringify(v));
  }
  if (sg.cruces.length) {
    await pg.evaluate(() => window.scrollTo(0, 0));
    await pg.click('#b-sigue [data-ir-llave="' + sg.cruces[sg.cruces.length - 1] + '"]');
    await pg.waitForTimeout(1500);
    const v = await pg.evaluate(k => { const a = document.querySelector('.llave[data-llave="' + k + '"]').getBoundingClientRect(); return { top: Math.round(a.top), alto: window.innerHeight, hash: location.hash }; }, sg.cruces[sg.cruces.length - 1]);
    revisa(v.top >= 0 && v.top < v.alto * 0.6 && v.hash === '', etq + 'cada cruce del anuncio lleva a su serie en el cuadro', JSON.stringify(v));
  }
  if (extra.anuncio) revisa(sg.texto.includes(extra.anuncio), etq + 'el anuncio bajo la portada dice «' + extra.anuncio + '»', sg.texto);
  if (CAPTURAS && extra.foto) { await pg.evaluate(() => window.scrollTo(0, 0)); await pg.waitForTimeout(300); fs.mkdirSync(DIR_CAP, { recursive: true }); const pre = path.join(DIR_CAP, motor + '-' + (movil ? 'iphone' : 'escritorio') + '-' + extra.foto);
    await pg.screenshot({ path: pre + '-portada.png' }); await pg.locator('section.sigue').screenshot({ path: pre + '-sigue.png' }); }

  /* «Próximos partidos»: una tarjeta completa por partido pendiente y, si no tienen día ni hora, las piernas de liguilla como tarjetas compactas */
  const px = await pg.evaluate(() => {
    const sec = document.getElementById('proximos'), T = e => (e ? e.textContent : '').replace(/\s+/g, ' ').trim();
    return { oculto: sec.hidden, tarjetas: document.querySelectorAll('#b-partidos .partido').length, bajada: T(document.getElementById('proximos-bajada')), nota: T(document.getElementById('nota-sueltas')), notaComb: T(document.getElementById('nota-sin-combinada')),
      grupos: Array.from(document.querySelectorAll('#b-partidos .grupo > h3')).map(h => T(h)), indice: document.querySelectorAll('#b-indice .indice button').length, vacios: document.querySelectorAll('#proximos .vacio, #combinada .vacio').length,
      cards: Array.from(document.querySelectorAll('#b-partidos .pleg')).map(p => ({ cuando: T(p.querySelector('.cuando')), nombres: Array.from(p.querySelectorAll('.eq__n')).map(T), escudos: p.querySelectorAll('.duelo .esc').length,
        tablero: Array.from(p.querySelectorAll('.duelo .tablero b')).map(T).join('-'), x12: !!p.querySelector('.x12'), pcts: Array.from(p.querySelectorAll('.ley b')).map(T), pie: T(p.querySelector('.pleg__pie span')), serie: (p.querySelector('[data-serie]') || { getAttribute: () => '' }).getAttribute('data-serie'),
        cortados: Array.from(p.querySelectorAll('.eq__n')).filter(e => { const lh = parseFloat(getComputedStyle(e).lineHeight) || 16, renglones = Math.round(e.getBoundingClientRect().height / lh); return e.scrollWidth > e.clientWidth + 1 || renglones > e.textContent.trim().split(/\s+/).length; }).map(T),
        caja: (() => { const r = p.getBoundingClientRect(), q = p.querySelector('.pleg__pie').getBoundingClientRect(); return [Math.round(r.top), Math.round(r.bottom), Math.round(q.bottom)]; })() })) };
  });
  revisa(px.tarjetas === pend, etq + 'una tarjeta completa por partido pendiente (' + pend + ')', String(px.tarjetas));
  if (extra.plegs != null) revisa(sueltas.length === extra.plegs && px.cards.length === extra.plegs, etq + extra.plegs + ' tarjetas compactas de liguilla', sueltas.length + ' / ' + px.cards.length);
  if (!pend && !sueltas.length) revisa(px.oculto, etq + 'sin nada por jugar, la sección «Próximos partidos» se retira (no queda una pantalla vacía)', JSON.stringify(px).slice(0, 200));
  else revisa(!px.oculto && px.vacios === 0 && px.indice === pend + sueltas.length, etq + '«Próximos partidos» a la vista, con un botón en el índice por partido', JSON.stringify([px.oculto, px.vacios, px.indice]));
  const malasP = [];
  sueltas.forEach((x, i) => {
    const c = px.cards[i], l = x.l, m = l.marcador || {}, fase = { cuartos: 'Cuartos', semifinal: 'Semifinal', final: 'Final' }[x.s.fase], cuando = l.fecha_local ? null : ventanaTxt((x.r.fechas || {})[x.n === 2 ? 'vuelta' : 'ida']);
    const bien = !!c && c.cuando.startsWith(fase + ' · ' + (x.n === 2 ? 'Vuelta' : 'Ida')) && c.cuando.includes(x.s.llave) && (!cuando || c.cuando.endsWith(cuando)) && JSON.stringify(c.nombres) === JSON.stringify([l.local, l.visitante]) && c.escudos === 2 &&
      (!Number.isFinite(m.gl) || c.tablero === m.gl + '-' + m.gv) && c.x12 && JSON.stringify(c.pcts) === JSON.stringify([pctTxt(l.p_local), pctTxt(l.p_empate), pctTxt(l.p_visitante)]) && c.pie === ((l.estadio || {}).nombre || 'Sede por confirmar') && c.serie === x.s.llave;
    if (!bien) malasP.push(x.s.llave + '-' + x.n + ' ' + JSON.stringify(c));
  });
  if (sueltas.length) {
    revisa(px.cards.length === sueltas.length && malasP.length === 0, etq + 'las ' + sueltas.length + ' piernas de liguilla sin día ni hora como tarjetas compactas en orden (idas y luego vueltas): fase y pierna, llave, ventana de fechas, escudos, marcador más probable, 1X2 con sus %, sede y botón a la serie', px.cards.length + ' ' + malasP.slice(0, 2).join(' | '));
    revisa(/Día y hora por confirmar/i.test(px.nota) && /combinada de cuatro pronósticos de cada partido/.test(px.nota) && /cuando la liga confirme día y hora/.test(px.nota) && (pend || /^Lo que sigue: /.test(px.bajada)), etq + 'nota honesta: sin día ni hora, la combinada de cada partido se publica cuando la liga los confirme', px.nota + ' · ' + px.bajada);
    revisa(px.cards.every(c => c.cortados.length === 0), etq + 'en las tarjetas compactas ningún nombre se parte a media palabra ni se sale', JSON.stringify(px.cards.map(c => c.cortados).filter(x => x.length)));
    if (!movil) { /* en escritorio van de cuatro en cuatro: el pie (sede y botón) queda a la misma altura en cada renglón */
      const filas = {}; px.cards.forEach(c => { (filas[c.caja[0]] = filas[c.caja[0]] || []).push(c.caja); });
      revisa(Object.values(filas).every(f => f.every(k => Math.abs(k[1] - f[0][1]) <= 1 && Math.abs(k[2] - f[0][2]) <= 1)) && Object.values(filas).some(f => f.length >= 2), etq + 'tarjetas compactas en renglones parejos, con la sede y el botón alineados abajo', JSON.stringify(Object.values(filas).map(f => f.map(k => k.join('/')))));
    }
    /* el botón «Serie Cx» abre el detalle de esa serie en el cuadro */
    const k0 = sueltas[0].s.llave;
    await pg.click('#b-partidos .pleg [data-serie="' + k0 + '"]');
    await pg.waitForTimeout(1500);
    const dt = await pg.evaluate(() => { const d = document.getElementById('serie-det'), r = d.getBoundingClientRect(); return { sel: (document.querySelector('.llave--sel') || { getAttribute: () => '' }).getAttribute('data-llave'), legs: d.querySelectorAll('.leg').length, top: Math.round(r.top), alto: window.innerHeight, hash: location.hash }; });
    revisa(dt.sel === k0 && dt.legs === 2 && dt.top >= 0 && dt.top < dt.alto * 0.6 && dt.hash === '', etq + 'el botón de la tarjeta compacta abre el detalle de su serie (' + k0 + ') en el cuadro', JSON.stringify(dt));
  }
  if (!hayComb && !px.oculto) revisa(/combinada de la jornada/.test(px.nota + ' ' + px.notaComb), etq + 'sin combinada de la jornada, «Próximos partidos» dice por qué', px.nota + ' · ' + px.notaComb);
  const cb = await pg.evaluate(() => ({ oculto: document.getElementById('combinada').hidden, tabs: document.querySelectorAll('#combinada [role="tab"]').length }));
  revisa(hayComb ? !cb.oculto && cb.tabs >= 3 : cb.oculto, etq + (hayComb ? 'la combinada de la jornada con sus pestañas' : 'sin combinada de la jornada la sección se retira (no queda una pantalla vacía)'), JSON.stringify(cb));
  /* ninguna sección se queda en un estado vacío gigante */
  const vac = await pg.evaluate(() => Array.from(document.querySelectorAll('main > section.banda[id]')).filter(s => !s.hidden).map(s => { const c = s.querySelector('.interior.cuerpo') || s; return { id: s.id, n: c.innerText.trim().length, vacio: !!s.querySelector('.vacio') }; }).filter(x => x.n < 60 || (x.vacio && /^(proximos|combinada|liguilla)$/.test(x.id))));
  revisa(vac.length === 0, etq + 'ninguna sección visible se queda vacía', JSON.stringify(vac));
  await revisaMenu(pg, etq);

  /* el cuadro: cada serie con su estado (Definida si sus dos equipos ya son seguros; Proyectada si todavía es la ruta de los favoritos) */
  if (t) {
    const enPagina = await pg.evaluate(() => Array.from(document.querySelectorAll('#cuadro .llave')).map(l => [l.getAttribute('data-llave'), ((l.querySelector('.llave__id .chip') || {}).textContent || null)]));
    const esp = [].concat(...t.rondas.map(r => (r.series || []).map(s => [s.llave, chipEsperado(s, t)]))), mapa = Object.fromEntries(enPagina), chips = esp.map(x => [x[0], x[0] in mapa ? mapa[x[0]] : 'falta']);
    revisa(enPagina.length === esp.length && JSON.stringify(chips) === JSON.stringify(esp) && (!extra.chips || JSON.stringify(chips.map(x => x[1])) === JSON.stringify(extra.chips)), etq + 'cada serie del cuadro con su estado (' + esp.map(x => x[0] + ' ' + (x[1] || '—')).join(', ') + ')', JSON.stringify(chips));
    if (extra.estadoCuadro) { const ec = await pg.evaluate(() => document.querySelector('.cuadro-estado p').textContent); revisa(extra.estadoCuadro.test(ec), etq + 'el estado del cuadro dice qué rondas siguen siendo la ruta de los favoritos', ec); }
    if (!movil) {
      await pg.setViewportSize({ width: 1440, height: 900 }); await pg.waitForTimeout(300);
      const alto = await pg.evaluate(() => Math.round(document.getElementById('cuadro').getBoundingClientRect().height));
      revisa(alto <= 900 - 60, etq + 'cuadro en espejo a 1440x900: cabe en una pantalla', String(alto));
      await pg.setViewportSize(opciones.viewport); await pg.waitForTimeout(200);
    }
  }
  /* terminada la fase regular nada habla en futuro de ella */
  const rc = await pg.evaluate(() => { const T = e => (e ? e.textContent : '').replace(/\s+/g, ' ').trim();
    return { final: document.getElementById('b-final').hidden, finalTxt: T(document.getElementById('b-final')), cols: Array.from(document.querySelectorAll('#b-embudo thead th')).map(T), filas: document.querySelectorAll('#b-embudo tbody tr').length,
      notas: Array.from(document.querySelectorAll('#b-campeon .nota')).map(T), tabla: T(document.querySelector('#b-tabla h3')), bajada: T(document.getElementById('tabla-bajada')), cruces: T(document.getElementById('b-cruces')), camino: T(document.getElementById('camino-bajada')) }; });
  const texto = await textoVisible(pg);
  if (fin) {
    const cl = (d.liguilla && d.liguilla.clasificados) || d.tabla.slice(0, 8).map(r => r.equipo), fuera = d.tabla.filter(r => !cl.includes(r.equipo)).map(r => r.equipo);
    const viejo = /si la tabla termina como se espera|cerraría los cuartos|Así se espera que termine|Tabla final proyectada|Aún falta fase regular|Todavía falta fase regular|Los cuartos más probables|Lo que resta del torneo/i.exec(texto);
    revisa(rc.final && !rc.cols.includes('Liguilla') && rc.filas === cl.length && rc.notas.includes('No clasificaron a la liguilla: ' + fuera.join(', ') + '.') && !rc.notas.some(n => /Sin título en ninguna simulación/.test(n) && fuera.some(e => n.includes(e))) &&
      /Así terminó/.test(rc.tabla) && /Así terminó la fase regular/.test(rc.bajada) && /^La liguilla, jugada /.test(rc.camino) && !viejo,
      etq + 'fase regular terminada: tabla final (sin la proyección), «Hasta dónde llega cada uno» sólo con los ' + cl.length + ' clasificados y sin columna «Liguilla», los ' + fuera.length + ' que no clasificaron por su nombre y nada en futuro', JSON.stringify(rc).slice(0, 400) + (viejo ? ' · «' + viejo[0] + '»' : ''));
  } else revisa(!rc.final && /Así se espera que termine/.test(rc.finalTxt) && rc.cols.includes('Liguilla') && /Así va hoy/.test(rc.tabla), etq + 'fase regular en juego: tabla de hoy, tabla final proyectada y probabilidad de clasificar', JSON.stringify(rc).slice(0, 300));
  await revisaConexion(pg, etq);
  const desb = await desbordes(pg), mala = palabrasMalas(texto), resp = await pg.evaluate(() => document.querySelectorAll('.respaldo').length);
  revisa(desb.sw <= desb.ancho + 1 && desb.malos.length === 0, etq + 'sin desplazamiento horizontal ni elementos fuera de la pantalla', desb.sw + ' ' + desb.malos.join(' | '));
  revisa(!mala && resp === 0 && errores.length === 0, etq + 'sin "undefined"/"NaN"/"null", sin bloques de respaldo y sin errores de consola', (mala || '') + ' ' + resp + ' ' + errores.slice(0, 3).join(' || '));
  if (CAPTURAS && extra.foto && px.cards.length) { await pg.evaluate(() => document.getElementById('proximos').scrollIntoView()); await pg.waitForTimeout(800); const b = await pg.locator('#proximos').boundingBox(), y = await pg.evaluate(() => window.pageYOffset); await pg.screenshot({ path: path.join(DIR_CAP, motor + '-' + (movil ? 'iphone' : 'escritorio') + '-' + extra.foto + '-proximos.png'), fullPage: true, clip: { x: 0, y: b.y + y, width: pg.viewportSize().width, height: Math.min(b.height, 3000) } }); }
  await pg.close();
  return { d, t, sueltas };
}
/* variantes de la copia fija «definido» (todas INVENTADAS a partir de ella): la serie la gana su favorito con marcadores a modo */
function decidirSerie(s, base) {
  const fav = s.favorito, mejorGana = fav === s.mejor.equipo;
  s.real = true; s.definida = true; s.decidida = true; s.ganador = fav; s.alternativas = [];
  s.p_avanza_mejor = mejorGana ? 1 : 0; s.p_avanza_peor = 1 - s.p_avanza_mejor; s.p_favorito = 1;
  s.global = { probable: null, top: [], p_gana_mejor: null, p_empate: null, p_gana_peor: null };
  s.piernas.forEach((l, j) => { /* ida en casa del peor sembrado, vuelta en la del mejor: gana el favorito en el global */
    Object.assign(l, { id: base + j, fecha_utc: null, fecha_local: null, hora_local: null, jugado: true, gl: mejorGana ? (j ? 1 : 0) : (j ? 1 : 2), gv: mejorGana ? (j ? 0 : 1) : (j ? 1 : 0) });
    COMO_PRONOSTICO.forEach(k => delete l[k]);
  });
}
function conSemisDefinidas(d) { /* los cuatro cuartos jugados (ganan los favoritos): las dos semifinales ya tienen sus equipos; la final sigue proyectada */
  const t = d.liguilla.torneo;
  t.rondas[0].series.forEach((s, i) => decidirSerie(s, 990000100 + 10 * i));
  t.rondas[1].series.forEach(s => { s.definida = true; s.alternativas = []; });
  t.rondas[2].series[0].definida = false;
  d.liguilla.en_curso = true; t.estado = 'en_curso';
}
function conLiguillaTerminada(d) {
  conSemisDefinidas(d);
  const t = d.liguilla.torneo;
  t.rondas[1].series.forEach((s, i) => decidirSerie(s, 990000200 + 10 * i));
  t.rondas[2].series[0].definida = true; decidirSerie(t.rondas[2].series[0], 990000300);
  t.estado = 'terminado'; t.campeon_decidido = true; t.campeon_ruta = t.rondas[2].series[0].ganador; d.liguilla.en_curso = false;
}
function conIdasProgramadas(d, fijo) { /* ESPN ya lista las 4 idas (pronóstico completo, copiado de los partidos del documento fijo); las vueltas siguen sin día ni hora */
  d.pendientes = d.liguilla.torneo.rondas[0].series.map((s, i) => {
    const l = s.piernas[0], p = copia(fijo.pendientes[i]);
    return Object.assign(p, { id: 990000400 + i, local: l.local, visitante: l.visitante, fase: 'cuartos', pierna: 1, etiqueta: 'Cuartos de final, ida', fecha_utc: (i < 2 ? '2026-11-26' : '2026-11-27') + 'T0' + (i % 2 ? 3 : 1) + ':00:00+00:00', fecha_local: i < 2 ? '2026-11-25' : '2026-11-26', hora_local: i % 2 ? '21:00' : '19:00' });
  });
}

async function correr(navegador, nombre, opciones) {
  console.log('\n== ' + motor + ' · ' + nombre + ' ==');
  const movil = nombre === 'iphone';
  const ctx = await navegador.newContext(Object.assign({ ignoreHTTPSErrors: true, locale: 'es-MX' }, opciones));
  const errores = [];
  const page = await abrir(ctx, errores);
  await page.clock.install({ time: new Date(AHORA_FIJO) });       /* sus 9 partidos siguen por jugar: cuenta regresiva y «Próximo partido» */
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
  await revisaConexion(page, '');

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
  await revisaMenu(page, '');
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
  await px.clock.runFor(400);                                     /* la base simulada entrega 150 ms después de suscribirse: se avanza el reloj simulado en vez de confiar en el real */
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
    return { llaves: document.querySelectorAll('#cuadro .llave').length, tarjetas: document.querySelectorAll('.partido').length, pendientes: JSON.parse(document.getElementById('datos').textContent).pendientes.length, respaldos: document.querySelectorAll('.respaldo').length,
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
  revisa(v.tarjetas === v.pendientes && v.tarjetas >= 3 && v.respaldos === 0 && errL.length === 0, 'variante: datos en null no rompen nada', JSON.stringify([v.tarjetas, v.pendientes, v.respaldos]) + ' ' + errL.slice(0, 3).join(' || '));
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

  /* ---------- desempeño: modelo contra mercado sellado ---------- */
  await mercadoSellado(ctx, capElDe);

  /* ---------- la página según el estado de SUS datos: los de hoy, la copia fija «definido» y sus variantes ---------- */
  await revisaSegunDatos(ctx, URL_REAL, 'datos de hoy', movil, opciones, { pantalla: true, foto: 'hoy' });
  const DEF = ['Definida', 'Definida', 'Definida', 'Definida', 'Proyectada', 'Proyectada', 'Proyectada'];
  const def = await revisaSegunDatos(ctx, URL_DEFINIDO, 'copia fija «definido»', movil, opciones,
    { pantalla: true, ahora: AHORA_DEFINIDO, foto: 'definido', plegs: 8, chips: DEF, anuncio: 'Del 25 al 29 de noviembre', estadoCuadro: /Semifinales y final siguen la ruta de los favoritos/ });
  const sd = def.t.rondas.map(r => r.series.map(x => x.definida));
  revisa(def.t.estado === 'definido' && JSON.stringify(sd) === JSON.stringify([[true, true, true, true], [false, false], [false]]), 'copia fija «definido»: el exportador marca «definida» los cuartos (tabla final) y no las semifinales ni la final', JSON.stringify(sd));
  const fijo = datosDocumento(DOC_FIJO);
  await revisaSegunDatos(ctx, variante('sindefinida', d => { torneoDe(d).rondas.forEach(r => r.series.forEach(x => { delete x.definida; })); }, DOC_DEFINIDO), 'datos viejos sin el campo «definida»', movil, opciones, { ahora: AHORA_DEFINIDO, plegs: 8, chips: DEF });
  await revisaSegunDatos(ctx, variante('idas', d => conIdasProgramadas(d, fijo), DOC_DEFINIDO), 'idas de cuartos ya en el calendario', movil, opciones, { ahora: AHORA_DEFINIDO, plegs: 4, chips: DEF, foto: 'idas' });
  await revisaSegunDatos(ctx, variante('semis', conSemisDefinidas, DOC_DEFINIDO), 'cuartos jugados y semifinales definidas', movil, opciones,
    { ahora: AHORA_DEFINIDO, foto: 'semis', plegs: 4, anuncio: 'Semifinales', chips: ['Terminada', 'Terminada', 'Terminada', 'Terminada', 'Definida', 'Definida', 'Proyectada'], estadoCuadro: /La final sigue la ruta de los favoritos\.$/ });
  await revisaSegunDatos(ctx, variante('terminada', conLiguillaTerminada, DOC_DEFINIDO), 'liguilla terminada', movil, opciones, { ahora: AHORA_DEFINIDO, foto: 'terminada', plegs: 0, chips: ['Terminada', 'Terminada', 'Terminada', 'Terminada', 'Terminada', 'Terminada', 'Terminada'] });
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

/* Desempeño sellado, modelo contra mercado: datos de hoy y variantes (ver conMercado). Todo lo que se revisa es formato:
   las cifras esperadas son las que trae el documento, nunca algo que la página tenga que calcular. */
async function mercadoSellado(ctx, capElDe) {
  const errM = [];
  const pb = await abrir(ctx, errM);
  await pb.goto(URL_REAL, { waitUntil: 'load' });                    /* lo exportado hoy */
  await pb.waitForTimeout(400);
  const hoy = datosDocumento(DOC_REAL), real = datosDocumento(DOC_FIJO), cmR = (hoy.desempeno || {}).contra_mercado || {}, mb = await leeMercado(pb);
  const marcas = us => us.map(u => !u.pronostico ? '' : u.pronostico.mercado ? 'si' : u.pronostico.origen === 'sello' ? 'no' : '');
  revisa(typeof cmR.n === 'number' && mb.hay && mb.enDesempeno && mb.lectura === cmR.lectura && /Modelo contra mercado/.test(mb.texto) && mb.respaldos === 0, 'mercado sellado: el documento exportado trae desempeno.contra_mercado y la página lo muestra dentro del desempeño sellado', JSON.stringify([cmR.n, mb.hay, mb.lectura]));
  if (cmR.n > 0) {
    const esp = [String(cmR.n), cmR.modelo.logloss.toFixed(3), cmR.mercado.logloss.toFixed(3)];
    revisa(mb.datos.length === 4 && esp.every((x, i) => mb.datos[i][1] === x) && /no los de cierre/.test(mb.texto) && (cmR.lectura === 'pocos_partidos') === /no se puede concluir nada/.test(mb.texto),
      'mercado sellado (datos de hoy): ' + cmR.n + ' partidos comparados con el log-loss de los dos tal como se exportó' + (cmR.lectura === 'pocos_partidos' ? ', y la advertencia de que no se puede concluir nada' : ''), JSON.stringify(mb.datos) + ' ' + mb.texto.slice(0, 200));
  } else {
    const desde = cmR.desde_local ? fechaCortaEsperada(cmR.desde_local) : null;
    revisa(mb.datos.length === 0 && !/Log-loss del mercado/.test(mb.texto) && (desde ? mb.texto.includes('se guardan en su sello desde el ' + desde) && (cmR.n_sellados_con_mercado > 0) === mb.texto.includes(cmR.n_sellados_con_mercado === 1 ? 'los trae 1 partido pendiente' : 'los traen ' + cmR.n_sellados_con_mercado + ' partidos pendientes') : /ningún sello trae momios/.test(mb.texto)),
      'mercado sellado (datos de hoy): sin partidos comparados no hay cifras, sólo ' + (desde ? 'desde cuándo se guardan los momios (' + desde + ') y cuántos partidos pendientes los traen (' + cmR.n_sellados_con_mercado + ')' : 'el aviso de que ningún sello trae momios todavía'), mb.texto);
  }
  revisa(JSON.stringify(mb.tarjetas.map(x => x.marca)) === JSON.stringify(marcas(hoy.ultimos_resultados)), 'mercado sellado (datos de hoy): cada resultado dice si su sello guardó momios; los que no vienen de un sello no dicen nada', JSON.stringify(mb.tarjetas.map(x => x.marca)));
  await pb.close();

  /* tres partidos comparados (cifras INVENTADAS; son las del caso a mano de produccion/pruebas/test_sellos_mercado.py), sobre el documento fijo */
  const pm = await abrir(ctx, errM);
  await pm.goto(variante('mercado', d => conMercado(d, 3)), { waitUntil: 'load' });
  await pm.waitForTimeout(400);
  const m3 = await leeMercado(pm), u0 = real.ultimos_resultados[0], k0 = u0.resultado, ll0 = -Math.log(P_MODELO[k0]), llm0 = -Math.log(P_MERCADO[k0]);
  revisa(m3.hay && m3.enDesempeno && m3.lectura === 'pocos_partidos' && JSON.stringify(m3.datos.map(x => x[1])) === JSON.stringify(['3', '1.265', '1.304', '−0.039 ± 0.164']) && /Diferencia \(modelo − mercado\)/.test(m3.datos[3][0]),
    'modelo contra mercado: partidos comparados, log-loss del modelo y del mercado y la diferencia con su error estándar, tal como vienen en los datos', JSON.stringify(m3.datos));
  revisa(/Con 3 partidos no se puede concluir nada/.test(m3.texto) && /al menos 30 partidos/.test(m3.texto) && /Los mismos 3 partidos/.test(m3.texto) && /no los de cierre/.test(m3.texto) && /desde el 16 nov 2026/.test(m3.texto) && /Quedan fuera 1 partido calificado/.test(m3.texto) && /modelo 1 de 3 · favorito del mercado 2 de 3/.test(m3.texto) && /una diferencia positiva favorece al mercado/.test(m3.texto) && /El ± es el error estándar de esa diferencia/.test(m3.texto),
    'modelo contra mercado: texto franco (con 3 partidos no se puede concluir nada; momios al sellar, no de cierre; cuántos quedan fuera; aciertos de cada uno)', m3.texto);
  const t0 = m3.tarjetas[0] || { texto: '' }, cerca = llm0 < ll0 ? 'más cerca el mercado' : llm0 > ll0 ? 'más cerca el modelo' : 'quedaron iguales';
  revisa(t0.marca === 'si' && t0.barras === 2 && t0.texto.includes('Mercado al sellar (Casa de prueba)') && t0.texto.includes('40.0%30.0%30.0%') && t0.texto.includes('El mercado le daba ' + (P_MERCADO[k0] * 100).toFixed(1) + '% a lo que pasó') && t0.texto.includes('modelo ' + ll0.toFixed(3) + ', mercado ' + llm0.toFixed(3)) && t0.texto.includes(cerca),
    'resultado con mercado sellado: barra del mercado junto a la del modelo, sus tres probabilidades y el log-loss de los dos en ese partido', t0.texto);
  revisa((m3.tarjetas[1] || {}).marca === 'no' && m3.tarjetas[1].barras === 1 && /el sello de este partido no guardó momios/.test(m3.tarjetas[1].texto) && (m3.tarjetas[2] || {}).marca === '' && !/[Mm]ercado/.test(m3.tarjetas[2].texto),
    'resultado sin mercado sellado: lo dice si viene de un sello y calla si el pronóstico no es sellado', JSON.stringify(m3.tarjetas.slice(1, 3)));
  const desbM = await desbordes(pm), malaM = palabrasMalas(m3.texto + ' ' + m3.tarjetas.map(x => x.texto).join(' ') + ' ' + m3.textoDesempeno);
  revisa(desbM.sw <= desbM.ancho + 1 && desbM.malos.length === 0 && !malaM && m3.respaldos === 0 && errM.length === 0, 'modelo contra mercado: sin desbordes, sin "undefined"/"NaN"/"null" y sin errores', desbM.sw + ' ' + desbM.malos.join(' | ') + (malaM || '') + errM.slice(0, 2).join('|'));
  await capElDe(pm)('15-contra-mercado', '#contra-mercado', 900);
  await capElDe(pm)('15b-resultado-con-mercado', '#b-ultima .res', 700);
  await pm.close();

  /* un solo partido (sin error estándar) y cuarenta con el mercado claramente mejor */
  const p1m = await abrir(ctx, errM);
  await p1m.goto(variante('mercado1', d => conMercado(d, 1)), { waitUntil: 'load' });
  await p1m.waitForTimeout(300);
  const m1 = await leeMercado(p1m);
  revisa(m1.lectura === 'pocos_partidos' && m1.datos.length === 4 && m1.datos[0][1] === '1' && m1.datos[3][1] === '+0.288' && /Con un solo partido la diferencia no tiene error estándar/.test(m1.texto) && !/±/.test(m1.texto) && /Con 1 partido no se puede concluir nada/.test(m1.texto) && /El mismo partido/.test(m1.texto) && !/Quedan fuera/.test(m1.texto) && !palabrasMalas(m1.texto),
    'modelo contra mercado con un solo partido: diferencia sin error estándar (no se inventa) y la misma advertencia', JSON.stringify(m1.datos) + ' ' + m1.texto.slice(0, 160));
  await p1m.close();
  const p40 = await abrir(ctx, errM);
  /* el nombre de la casa viene de ESPN: uno larguísimo y sin espacios (INVENTADO) no debe ensanchar la tarjeta del resultado */
  const CASA_LARGA = 'Casa de apuestas ' + 'Sportsbook'.repeat(7);
  await p40.goto(variante('mercado40', d => { conMercado(d, 40); d.ultimos_resultados[0].pronostico.mercado.proveedor = CASA_LARGA; }), { waitUntil: 'load' });
  await p40.waitForTimeout(300);
  const m40 = await leeMercado(p40);
  const caja40 = await p40.evaluate(() => { const r = document.querySelector('#b-ultima .res [data-mercado="si"]'), t = r && r.closest('.res'); return t ? [Math.round(t.getBoundingClientRect().right), Math.round(r.querySelector('span').getBoundingClientRect().right), window.innerWidth] : null; });
  revisa(m40.lectura === 'mercado_mejor' && m40.datos[0][1] === '40' && m40.datos[3][1] === '+0.031 ± 0.012' && /Con 40 partidos el mercado va mejor/.test(m40.texto) && !/no se puede concluir nada/.test(m40.texto) && !palabrasMalas(m40.texto) &&
    !!caja40 && caja40[0] <= caja40[2] + 1 && caja40[1] <= caja40[0] + 1 && m40.tarjetas[0].texto.includes(CASA_LARGA),
    'modelo contra mercado con 40 partidos: la lectura (mercado mejor por más de dos errores estándar) viene de los datos, no la decide la página; y una casa de nombre larguísimo no ensancha la tarjeta del resultado', m40.texto.slice(-260) + ' ' + JSON.stringify(caja40));
  await p40.close();

  /* sin ningún sello con momios, documento viejo sin el campo y datos rotos: nada se cae */
  const pv0 = await abrir(ctx, errM);
  await pv0.goto(variante('mercado0', d => { d.desempeno.acumulado = { n: 0 }; d.desempeno.n_calificados = 0; d.desempeno.contra_mercado = MERCADO_VACIO(null, 0); d.ultimos_resultados.forEach(u => { if (u.pronostico) delete u.pronostico.mercado; }); }), { waitUntil: 'load' });
  await pv0.waitForTimeout(300);
  const m0 = await leeMercado(pv0);
  revisa(m0.hay && m0.enDesempeno && m0.lectura === 'sin_partidos' && m0.datos.length === 0 && /Todavía ningún sello trae momios del mercado/.test(m0.texto) && /Todavía no hay partidos calificados/.test(m0.textoDesempeno) && !palabrasMalas(m0.textoDesempeno) && m0.respaldos === 0,
    'modelo contra mercado sin ningún sello con momios (y sin partidos calificados): una línea que lo dice, sin cifras', m0.textoDesempeno.slice(-260));
  await pv0.close();
  const errRoto = [];
  const pvr = await abrir(ctx, errRoto);
  await pvr.goto(variante('mercadoroto', d => { delete d.desempeno.contra_mercado; d.ultimos_resultados[0].pronostico = Object.assign({}, PRON_PRUEBA(d.ultimos_resultados[0].resultado), { mercado: { proveedor: 7, p_local: 'x', p_empate: null, logloss: 'y' } }); if (d.ultimos_resultados[1]) d.ultimos_resultados[1].pronostico = Object.assign({}, PRON_PRUEBA(d.ultimos_resultados[1].resultado), { mercado: 'no es un objeto' }); }), { waitUntil: 'load' });
  await pvr.waitForTimeout(300);
  const mr = await leeMercado(pvr);
  revisa(!mr.hay && mr.respaldos === 0 && errRoto.length === 0 && mr.tarjetas.length === real.ultimos_resultados.length && mr.tarjetas[0].marca === '' && mr.tarjetas[0].barras === 1 && /Resultado (acertado|fallado)/.test(mr.tarjetas[0].texto) && !palabrasMalas(mr.tarjetas.map(x => x.texto).join(' ') + mr.textoDesempeno) && /Desempeño sellado/.test(mr.textoDesempeno),
    'documento viejo sin contra_mercado y mercado sellado con basura: el bloque no sale, las tarjetas siguen con el pronóstico del modelo y nada se rompe', JSON.stringify(mr.tarjetas.slice(0, 2)) + errRoto.slice(0, 2).join('|'));
  await pvr.close();
}

(async () => {
  /* --vivo (opción de prueba) incrusta el documento en vivo sólo en documento.html; después se construye la página normal */
  const indice = path.join(WEB, 'index.html'), huella = f => fs.existsSync(f) ? fs.statSync(f).mtimeMs : 0;
  const antesIndice = huella(indice);
  execFileSync('python3', [path.join(WEB, 'construir.py'), '--vivo', path.join(WEB, '..', 'salidas', 'vivo_ejemplo.json')], { stdio: 'pipe' });
  const conVivo = fs.readFileSync(path.join(WEB, 'documento.html'), 'utf8'), intacto = huella(indice) === antesIndice;
  execFileSync('python3', [path.join(WEB, 'construir.py'), '--documento', '--salida', WEB], { stdio: 'inherit' });
  /* los dos documentos fijos (otro estado del torneo): --solo-documento no toca index.html, archivos_publicados.json ni capacidades.json */
  const publicados = path.join(WEB, 'archivos_publicados.json'), huellas = () => [indice, publicados, path.join(WEB, 'capacidades.json')].map(huella).join();
  const antesFijos = huellas();
  for (const [datos, doc] of [[DATOS_FIJO, DOC_FIJO], [DATOS_DEFINIDO, DOC_DEFINIDO]]) {
    temporales.push(doc);
    execFileSync('python3', [path.join(WEB, 'construir.py'), '--datos', datos, '--solo-documento', doc], { stdio: 'pipe' });
  }
  const fijosBien = huellas() === antesFijos && [DOC_FIJO, DOC_DEFINIDO].every(f => fs.existsSync(f) && /^<!doctype html>/i.test(fs.readFileSync(f, 'utf8').slice(0, 40)));
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
  revisa(fijosBien, 'construir.py --datos … --solo-documento arma los dos documentos fijos de prueba y no toca index.html, archivos_publicados.json ni capacidades.json');
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
