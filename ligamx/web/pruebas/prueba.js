#!/usr/bin/env node
/* Pruebas de la página de Cerebro Liga MX con Playwright.

   Uso (desde cualquier carpeta):
     PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node web/pruebas/prueba.js chromium [--capturas]
     PLAYWRIGHT_BROWSERS_PATH=<carpeta con webkit> node web/pruebas/prueba.js webkit [--capturas]

   Reconstruye la página (construir.py --documento --salida web/), la abre con file:// desde web/ en
   iPhone 13 y en escritorio 1440x900 y revisa: sin errores de consola, sin desplazamiento horizontal,
   una tarjeta por partido pendiente, pestañas de combinada, menú, imágenes, textos sin "undefined",
   "NaN" ni "null", video de portada, movimiento reducido y una variante con liguilla en curso y datos
   opcionales en null. Con --capturas guarda PNG en web/pruebas/capturas/. Sale con código 1 si algo falla. */
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
const VARIANTE = path.join(WEB, '_variante_prueba.html');
const fallas = [];
let revisados = 0;

function revisa(cond, nombre, detalle) {
  revisados++;
  if (!cond) { fallas.push(nombre + (detalle ? ' → ' + detalle : '')); console.log('  FALLA  ' + nombre + (detalle ? ' → ' + detalle : '')); }
  else console.log('  ok     ' + nombre);
}

/* documento con la liguilla en curso (ejemplo del CONTRATO) y varios opcionales en null */
function escribirVariante() {
  const doc = fs.readFileSync(path.join(WEB, 'documento.html'), 'utf8');
  const re = /(<script type="application\/json" id="datos">)([\s\S]*?)(<\/script>)/;
  const d = JSON.parse(re.exec(doc)[2]);
  d.liguilla.en_curso = true;
  d.liguilla.clasificados = ['Cruz Azul', 'América', 'Chivas', 'Santos', 'Toluca', 'Atlas', 'Pachuca', 'Tijuana'];
  d.liguilla.series = [{
    fase: 'cuartos', mejor: 'Cruz Azul', peor: 'Pachuca', siembra_mejor: 1, siembra_peor: 8,
    piernas: [
      { pierna: 1, id: 990000000, fecha_utc: '2026-11-26T01:00:00+00:00', local: 'Pachuca', visitante: 'Cruz Azul', jugado: true, gl: 1, gv: 0 },
      { pierna: 2, id: 990000001, fecha_utc: '2026-11-29T01:00:00+00:00', local: 'Cruz Azul', visitante: 'Pachuca', jugado: false, lam_l: 1.7583, lam_v: 1.1389,
        p_local: 0.5188, p_empate: 0.235, p_visitante: 0.2462, marcadores: [{ gl: 1, gv: 1, prob: 0.1105 }, { gl: 2, gv: 1, prob: 0.0971 }] }],
    decidida: false, ganador: null, p_avanza_mejor: 0.5188, p_avanza_peor: 0.4812, p_global_mejor: 0.2862, p_global_empate: 0.2326, p_global_peor: 0.4812,
    globales: [{ mejor: 1, peor: 2, prob: 0.1105 }, { mejor: 2, peor: 2, prob: 0.0971 }], regla_empate: 'avanza el mejor sembrado', p_avanza_mejor_sim: 0.5139, n_sim_cruce: 20000
  }, { fase: 'semifinal', mejor: 'América', peor: 'Toluca', siembra_mejor: 2, siembra_peor: 5, piernas: [], decidida: true, ganador: 'América', p_avanza_mejor: null, p_avanza_peor: null, globales: null, regla_empate: null }];
  /* datos raros: opcionales en null, ficha sin detalle, equipo sin escudo, sede sin fotos */
  const p0 = d.pendientes[0];
  p0.momios = null; p0.combinadas = null; p0.contexto = null; p0.explica = null; p0.mercados = null; p0.top5 = null; p0.lam_l = null;
  const p1 = d.pendientes[1];
  p1.combinadas.atrevida = null; p1.contexto.historial = null; p1.contexto.suspendidos_local = null; p1.contexto.sede = null; p1.estadio = { nombre: 'Sede nueva', ciudad: null, slug: 'no-existe', altitud_m: null };
  p1.fase = 'cuartos'; p1.pierna = 1; p1.etiqueta = 'Cuartos de final, ida'; p1.visitante = 'Equipo Nuevo';
  const p2 = d.pendientes[2];
  ['lam_l', 'lam_v', 'rho', 'top5', 'matriz', 'mercados', 'combinadas', 'explica', 'contexto', 'momios'].forEach(k => delete p2[k]); p2.detalle = false;
  d.combinada_jornada = null; d.calibracion_series = null; d.ultimos_resultados[0].pronostico = null;
  d.meta.modelo.contra_referencias = null; d.meta.modelo.seleccion = null;
  d.desempeno.acumulado = { n: 12, aciertos_1x2: 6, acierto_1x2: 0.5, marcadores_exactos: 2, marcador_exacto: 0.1667, logloss: 1.02, ee_logloss: 0.05, brier: 0.6, rps: 0.2,
    prob_media_del_pick: 0.47, logloss_referencia_tercios: 1.0986, combinadas: { segura: { n: 12, completas: 5, frecuencia: 0.4167, prob_anunciada: 0.45, picks_acertados_media: 3.1 } } };
  d.dominios = d.dominios.filter(x => !(x.a === 'América' && x.b === 'Cruz Azul'));
  fs.writeFileSync(VARIANTE, doc.replace(re, (_, a, __, c) => a + JSON.stringify(d).replace(/<\//g, '<\\/') + c));
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

async function correr(navegador, nombre, opciones) {
  console.log('\n== ' + motor + ' · ' + nombre + ' ==');
  const ctx = await navegador.newContext(Object.assign({ ignoreHTTPSErrors: true, locale: 'es-MX' }, opciones));
  const page = await ctx.newPage();
  const errores = [];
  page.on('console', m => { if (m.type() === 'error') errores.push(m.text() + ' @ ' + (m.location().url || '')); });
  page.on('pageerror', e => errores.push('pageerror: ' + e.message));
  let fuentes = true;
  page.on('requestfailed', r => { if (/fonts\.(googleapis|gstatic)\.com/.test(r.url())) fuentes = false; });
  await page.goto(URL_DOC, { waitUntil: 'load' });
  await page.waitForTimeout(600);
  const cap = async (archivo, op) => { if (CAPTURAS) { fs.mkdirSync(DIR_CAP, { recursive: true }); await page.screenshot(Object.assign({ path: path.join(DIR_CAP, motor + '-' + nombre + '-' + archivo + '.png') }, op || {})); } };
  const capEl = async (archivo, sel, altoMax) => {
    if (!CAPTURAS) return;
    const el = page.locator(sel).first(); await el.scrollIntoViewIfNeeded(); await page.waitForTimeout(700);
    const b = await el.boundingBox(); if (!b) return;
    const y = await page.evaluate(() => window.pageYOffset);
    await cap(archivo, { fullPage: true, clip: { x: 0, y: Math.max(0, b.y + y - 8), width: page.viewportSize().width, height: Math.min(altoMax || 1500, b.height + 16) } });
  };

  // video de portada
  const video = await page.evaluate(async () => {
    const v = document.getElementById('video-portada'); if (!v) return null;
    for (let i = 0; i < 40 && v.readyState < 2; i++) await new Promise(r => setTimeout(r, 250));
    return { readyState: v.readyState, pausado: v.paused, muted: v.muted, error: v.error ? v.error.code : null };
  });
  revisa(video && video.readyState >= 2, 'video de portada con readyState >= 2', JSON.stringify(video));
  await cap('1-portada');

  // estructura
  const n = await page.evaluate(() => ({ tarjetas: document.querySelectorAll('.partido').length, pendientes: JSON.parse(document.getElementById('datos').textContent).pendientes.length,
    respaldos: document.querySelectorAll('.respaldo').length, estadios: document.querySelectorAll('.estadio').length, h1: document.querySelectorAll('h1').length }));
  revisa(n.tarjetas === n.pendientes && n.tarjetas > 0, 'una tarjeta por partido pendiente', n.tarjetas + ' de ' + n.pendientes);
  revisa(n.respaldos === 0, 'ningún bloque en modo respaldo', String(n.respaldos));
  revisa(n.estadios === 16, 'galería con los 16 estadios', String(n.estadios));
  revisa(n.h1 === 1, 'un solo h1');

  // pestañas de la combinada del primer partido
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

  // menú de tres barras: abre, Escape lo cierra, elegir sección lo cierra y desplaza
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
  await page.waitForTimeout(1600);
  const tras = await page.evaluate(() => ({ cerrado: document.getElementById('menu').hidden, top: Math.round(document.getElementById('estadios').getBoundingClientRect().top), hash: location.hash }));
  revisa(tras.cerrado && Math.abs(tras.top) < 120 && tras.hash === '', 'elegir sección cierra el menú y desplaza sin tocar location.hash', JSON.stringify(tras));

  // recorre la página para disparar la carga diferida y revisa imágenes
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

  // galería: cambiar de foto
  const gal = await page.evaluate(() => { const b = document.querySelectorAll('.estadio [data-foto]')[1]; const im = b.closest('figure').querySelector('img'); const a = im.getAttribute('src'); b.click(); return { cambia: im.getAttribute('src') !== a, pres: b.getAttribute('aria-pressed') }; });
  revisa(gal.cambia && gal.pres === 'true', 'la galería de estadios cambia de foto');

  // capturas de secciones
  await page.evaluate(() => { const d = document.querySelector('.partido details'); if (d) d.open = true; });
  await capEl('3-partido', '.partido', 2600);
  await capEl('3b-porque', '.partido details', 2400);
  await capEl('4-camino', '#b-campeon', 1300);
  await capEl('4b-cruces', '#b-cruces', 1500);
  await capEl('5-tabla', '#b-tabla', 1300);
  await capEl('6-estadios', '#b-estadios', 1500);
  await capEl('7-modelo', '#b-fuerzas', 1400);
  await capEl('8-cab', '#camino .cab', 700);

  // desbordes: ni el documento ni ningún elemento visible se sale del ancho
  const desb = await page.evaluate(() => {
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
  revisa(desb.sw <= desb.ancho + 1, 'sin desplazamiento horizontal', desb.sw + ' > ' + desb.ancho);
  revisa(desb.malos.length === 0, 'ningún elemento se sale de la pantalla', desb.malos.join(' | '));

  const mala = palabrasMalas(await textoVisible(page));
  revisa(!mala, 'sin "undefined", "NaN" ni "null" en el texto', mala || '');
  revisa(errores.length === 0, 'sin errores de consola ni pageerror', errores.slice(0, 4).join(' || '));
  if (!fuentes) console.log('  nota   las fuentes de Google no cargaron en esta máquina: se probó con la pila de respaldo');
  else console.log('  nota   fuente de titulares cargada: ' + await page.evaluate(() => document.fonts.check('900 40px "Big Shoulders Display"')));

  // variante: liguilla en curso y opcionales en null
  const errV = [];
  const pv = await ctx.newPage();
  pv.on('console', m => { if (m.type() === 'error') errV.push(m.text()); });
  pv.on('pageerror', e => errV.push('pageerror: ' + e.message));
  await pv.goto('file://' + VARIANTE, { waitUntil: 'load' });
  await pv.waitForTimeout(400);
  const v = await pv.evaluate(() => ({ series: document.querySelectorAll('.serie').length, tarjetas: document.querySelectorAll('.partido').length, respaldos: document.querySelectorAll('.respaldo').length,
    cuadroVisible: !document.getElementById('b-cuadro').hidden, sw: document.documentElement.scrollWidth, ancho: window.innerWidth, grupos: Array.from(document.querySelectorAll('#b-partidos .grupo > h3')).map(h => h.textContent) }));
  revisa(v.series === 2 && v.cuadroVisible, 'variante: el cuadro real de la liguilla aparece', JSON.stringify(v));
  revisa(v.tarjetas === 10 && v.respaldos === 0 && errV.length === 0, 'variante: datos en null no rompen nada', JSON.stringify(v) + ' ' + errV.slice(0, 3).join(' || '));
  revisa(v.grupos.includes('Cuartos de final, ida'), 'variante: los partidos de liguilla forman su grupo', v.grupos.join(', '));
  revisa(v.sw <= v.ancho + 1, 'variante: sin desplazamiento horizontal');
  const malaV = palabrasMalas(await textoVisible(pv));
  revisa(!malaV, 'variante: sin "undefined", "NaN" ni "null"', malaV || '');
  if (CAPTURAS) { const el = pv.locator('#b-cuadro'); await el.scrollIntoViewIfNeeded(); await pv.waitForTimeout(500); await el.screenshot({ path: path.join(DIR_CAP, motor + '-' + nombre + '-9-liguilla.png') }); }
  await ctx.close();

  // movimiento reducido: sin autoplay ni animaciones
  const ctxR = await navegador.newContext(Object.assign({ ignoreHTTPSErrors: true }, opciones, { reducedMotion: 'reduce' }));
  const pr = await ctxR.newPage();
  await pr.goto(URL_DOC, { waitUntil: 'load' });
  await pr.waitForTimeout(700);
  const red = await pr.evaluate(() => { const v = document.getElementById('video-portada'); return { pausado: v.paused, autoplay: v.hasAttribute('autoplay'), animadas: document.querySelectorAll('.entra').length, poster: !!v.getAttribute('poster') }; });
  revisa(red.pausado && !red.autoplay && red.animadas === 0 && red.poster, 'movimiento reducido: video en pausa con póster y sin animaciones', JSON.stringify(red));
  await ctxR.close();
}

(async () => {
  execFileSync('python3', [path.join(WEB, 'construir.py'), '--documento', '--salida', WEB], { stdio: 'inherit' });
  const frag = fs.readFileSync(path.join(WEB, 'index.html'), 'utf8');
  const antes = frag.split('<script type="application/json"')[0];
  console.log('== archivo ==');
  revisa(!/<!doctype|<html[\s>]|<head[\s>]|<body[\s>]/i.test(antes), 'index.html es un fragmento (sin doctype, html, head ni body)');
  revisa(/^<title>Cerebro Liga MX<\/title>\s*<meta name="claude:viewport-fit-sides" content="cover">/.test(frag), 'empieza con <title> y la meta de la plataforma');
  revisa(!/<script[^>]+src=|<iframe|location\.hash|pushState|\balert\(|\bconfirm\(|\bprompt\(|localStorage/.test(antes + frag.split('</script>').pop()), 'sin scripts externos, iframes, hash, alert ni localStorage');
  const css = /<style>([\s\S]*?)<\/style>/.exec(frag)[1], raiz = /:root\{[\s\S]*?\n\}/.exec(css)[0];
  const literales = css.replace(raiz, '').match(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/g);
  revisa(!literales, 'ningún color literal fuera de los tokens de :root', (literales || []).slice(0, 5).join(' '));
  const usados = JSON.parse(fs.readFileSync(path.join(WEB, 'archivos_publicados.json'), 'utf8'));
  revisa(usados.length > 0 && usados.every(r => fs.existsSync(path.join(WEB, r))), 'archivos_publicados.json: los ' + usados.length + ' archivos existen');
  escribirVariante();

  const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
  const navegador = await pw[motor].launch(proxy ? { proxy: { server: proxy } } : {});
  try {
    await correr(navegador, 'iphone', pw.devices['iPhone 13']);
    await correr(navegador, 'escritorio', { viewport: { width: 1440, height: 900 } });
  } finally {
    await navegador.close();
    try { fs.unlinkSync(VARIANTE); } catch (e) { /* ya no estaba */ }
  }
  console.log('\n' + (fallas.length ? 'FALLARON ' + fallas.length + ' de ' + revisados + ':\n - ' + fallas.join('\n - ') : 'TODO BIEN: ' + revisados + ' revisiones en ' + motor));
  process.exit(fallas.length ? 1 : 0);
})().catch(e => { console.error(e); try { fs.unlinkSync(VARIANTE); } catch (x) { /* nada */ } process.exit(1); });
