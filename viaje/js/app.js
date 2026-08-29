/* Viaje SoCal 2026 — lógica de la app. Sin dependencias. */
(function () {
'use strict';

const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

/* ---------- almacenamiento ---------- */
const KEY = 'socal2026';
const store = {
  read() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } },
  write(o) { try { localStorage.setItem(KEY, JSON.stringify(o)); } catch (e) {} }
};
let S = Object.assign({ checks: {}, gastos: [], tc: TRIP.tipoCambioDefault, dia: null }, store.read());
const save = () => store.write(S);

/* ---------- fechas (hora del Pacífico, PDT = UTC-7 en septiembre) ---------- */
const PDT = '-07:00';
const at = (fecha, hhmm) => new Date(`${fecha}T${hhmm}:00${PDT}`);
const MES = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];

/* Devuelve el índice del día en curso, o -1 si el viaje no ha empezado / ya terminó. */
function diaActual() {
  const hoy = new Date();
  for (let i = 0; i < DIAS.length; i++) {
    const ini = at(DIAS[i].fecha, '00:00'), fin = at(DIAS[i].fecha, '23:59');
    if (hoy >= ini && hoy <= fin) return i;
  }
  return -1;
}

/* ================= CUENTA REGRESIVA ================= */
function pintaCuenta() {
  const ahora = new Date();
  const salida = new Date(TRIP.inicio);
  const fin = new Date(TRIP.fin);
  const lbl = $('#cdLbl'), big = $('#cdBig'), units = $('#cdUnits');

  if (ahora > fin) {
    lbl.textContent = 'El viaje';
    big.textContent = 'Terminó';
    units.innerHTML = '<div class="u"><b>¡Ojalá haya valido cada minuto!</b></div>';
    return;
  }
  const idx = diaActual();
  if (idx >= 0) {
    const d = DIAS[idx];
    lbl.textContent = `Día ${d.num} de 7 · ${d.dow} ${parseInt(d.fecha.slice(8), 10)}`;
    big.textContent = d.titulo;
    big.style.fontSize = '26px';
    units.innerHTML = '';
    return;
  }
  let ms = salida - ahora;
  const dd = Math.floor(ms / 864e5); ms -= dd * 864e5;
  const hh = Math.floor(ms / 36e5); ms -= hh * 36e5;
  const mm = Math.floor(ms / 6e4); ms -= mm * 6e4;
  const ss = Math.floor(ms / 1000);
  lbl.textContent = 'Faltan para el despegue';
  big.textContent = dd + (dd === 1 ? ' día' : ' días');
  units.innerHTML = [[hh,'horas'],[mm,'min'],[ss,'seg']]
    .map(([v, n]) => `<div class="u"><b>${String(v).padStart(2,'0')}</b><span>${n}</span></div>`).join('');
}

/* ================= HOY ================= */
function pintaHoy() {
  const idx = diaActual();
  const box = $('#hoyAhora');

  if (idx >= 0) {
    const d = DIAS[idx];
    const ahora = new Date();
    let sig = null;
    for (const b of d.bloques) {
      if (b.t === '—') continue;
      if (at(d.fecha, b.t) > ahora) { sig = b; break; }
    }
    box.innerHTML = `
      <div class="sec-t">Lo que sigue hoy</div>
      <div class="card">
        ${sig
          ? `<span class="pill p-or">${esc(sig.t)}</span>
             <h3 style="margin-top:9px">${esc(sig.titulo)}</h3>
             <p style="margin-top:5px">${esc(sig.texto || '')}</p>`
          : `<h3>Se acabó el guion de hoy</h3><p style="margin-top:5px">${esc(d.resumen)}</p>`}
        <button class="btn ghost" style="margin-top:12px;width:100%" data-goto="${idx}">Ver el día completo</button>
      </div>`;
  } else {
    box.innerHTML = `
      <div class="sec-t">El viaje en una frase</div>
      <div class="card">
        <p>Siete días, cuatro días de Disney, un partido de los Dodgers, dos cruces de frontera y una tarde de compras que cabe en 85 minutos. La app ya trae las horas límite marcadas.</p>
      </div>`;
  }

  /* candados: las horas que no se pueden mover */
  const candados = [
    { d:'Mar 8', h:'15:00', t:'Entrada a DCA con boleto de Oogie Boogie', n:'La fiesta corre 18:00–23:00.' },
    { d:'Mar 8', h:'13:40', t:'Hora límite de compras', n:'Es el único candado que depende de ti.' },
    { d:'Mié 9', h:'19:10', t:'Dodgers vs Rojos de Cincinnati', n:'Salir de Anaheim a las 16:15.' },
    { d:'Sáb 12', h:'~21:30', t:'Halloween Screams', n:'Verlo desde el hub, lado oeste.' },
    { d:'Sáb 12', h:'~22:30', t:'Fantasmic, 2º show', n:'Con tu área reservada de River Belle Terrace.' }
  ];
  $('#hoyCandados').innerHTML = candados.map(c => `
    <div class="card" style="display:flex;gap:13px;align-items:center;padding:13px 15px">
      <div style="flex:0 0 62px;text-align:center">
        <div style="font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--tx3);font-weight:700">${esc(c.d)}</div>
        <div style="font-size:16px;font-weight:800;color:var(--or)">${esc(c.h)}</div>
      </div>
      <div style="flex:1;min-width:0">
        <div style="font-size:14px;font-weight:600">${esc(c.t)}</div>
        <div style="font-size:12.5px;color:var(--tx2);margin-top:2px">${esc(c.n)}</div>
      </div>
    </div>`).join('');

  $('#hoyAlertas').innerHTML = ALERTAS.map(a => `
    <div class="al ${a.nivel}">
      <h4>${esc(a.titulo)}</h4>
      <p>${esc(a.detalle)}</p>
      <div class="fix"><b>Qué hacer</b>${esc(a.accion)}</div>
    </div>`).join('');
}

/* ================= RUTA ================= */
const ICONO = { vuelo:'✈️', cruce:'🛂', auto:'🚗', compras:'🛍️', hotel:'🏨', parque:'🎢',
                comida:'🍽️', show:'🎆', atraccion:'🎠', deporte:'⚾', ocio:'🌴', nota:'📌' };

function pintaDias() {
  $('#daySel').innerHTML = DIAS.map((d, i) => {
    const [y, m, dd] = d.fecha.split('-');
    const esHoy = diaActual() === i;
    return `<button class="dchip${S.dia === i ? ' on' : ''}${esHoy ? ' hoy' : ''}" data-d="${i}">
      <div class="dw">${esc(d.dow.slice(0,3))}</div>
      <div class="dn">${parseInt(dd,10)}</div>
      <div class="dm">${MES[parseInt(m,10)-1]}</div>
    </button>`;
  }).join('');
}

function pintaDia() {
  const d = DIAS[S.dia];
  if (!d) return;
  const pk = PARQUES[d.parque];
  $('#dayHead').innerHTML = `
    <span class="pill p-pu">${esc(d.badge)}</span>
    <h3 style="margin-top:9px;font-size:19px">${esc(d.titulo)}</h3>
    <p style="margin-top:4px;color:var(--tx3);font-size:13px">${esc(d.subtitulo)}</p>
    <p style="margin-top:10px">${esc(d.resumen)}</p>
    ${pk ? `<button class="btn ghost" style="margin-top:12px;width:100%" data-park="${esc(d.parque)}">Ver plan de ataque del parque</button>` : ''}`;

  /* Si el titulo ya empieza con emoji, no repetimos el icono del tipo. */
  const yaTieneEmoji = t => /^\p{Extended_Pictographic}/u.test(t);

  $('#dayTL').innerHTML = d.bloques.map(b => `
    <div class="ev${b.alerta ? ' alert' : ''}">
      <div class="time">${esc(b.t)}${b.t2 ? `<small>${esc(b.t2)}</small>` : ''}</div>
      <div class="dot"></div>
      <div class="body">
        <h4>${yaTieneEmoji(b.titulo) ? '' : `<span class="kind">${ICONO[b.kind] || '•'}</span>`}<span class="ttl">${esc(b.titulo)}</span></h4>
        ${b.texto ? `<div class="txt">${esc(b.texto)}</div>` : ''}
        ${b.why ? `<div class="why"><b>Por qué</b>${esc(b.why)}</div>` : ''}
      </div>
    </div>`).join('');
}

/* ================= PARQUES ================= */
let parkId = 'dca-obb';
function pintaParkSel() {
  $('#parkSel').innerHTML = Object.keys(PARQUES).map(k => {
    const corto = { 'dca-obb':'Oogie Boogie', 'dl-medio':'Disneyland ½', 'universal':'Universal',
                    'dca':'California Adv.', 'dl-completo':'Disneyland ⭐' }[k];
    return `<button class="pchip${parkId === k ? ' on' : ''}" data-p="${k}">${esc(corto)}</button>`;
  }).join('');
}
function pintaPark() {
  const p = PARQUES[parkId];
  $('#parkBody').innerHTML = `
    <div class="card">
      <h3 style="font-size:18px">${esc(p.nombre)}</h3>
      <p style="color:var(--or);font-weight:600;margin-top:4px;font-size:13px">${esc(p.fecha)}</p>
      <p style="margin-top:9px">${esc(p.horario)}</p>
      <div class="why" style="margin-top:11px;border-left-color:var(--or);background:rgba(255,138,61,.09);color:#f0cdb0">
        <b style="color:var(--or)">Lightning Lane</b>${esc(p.ll)}
      </div>
    </div>
    <div class="sec-t">Los principios del día</div>
    <div class="card"><ul class="bullets">${p.principios.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
    <div class="sec-t">Recorrido hora por hora</div>
    <div class="card"><div class="route">${p.ruta.map(s => `
      <div class="step ${s.tag || ''}">
        <div class="st">${esc(s.t)}</div>
        <div class="sc">
          <div class="sa">${esc(s.a)}</div>
          ${s.n ? `<div class="sn">${esc(s.n)}</div>` : ''}
        </div>
      </div>`).join('')}</div></div>
    <div class="sec-t">Lo que NO hay que hacer</div>
    <div class="card"><ul class="bullets no">${p.evitar.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
    <div class="sec-t">Trucos</div>
    <div class="card"><ul class="bullets">${p.oro.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

/* ================= LISTAS ================= */
const TICK = '<svg viewBox="0 0 12 12" fill="none"><path d="M1.5 6.2l3 3 6-6.4" stroke="#0d2a1e" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
function pintaListas() {
  $('#listasBody').innerHTML = CHECKLISTS.map(l => {
    const hechos = l.items.filter((_, i) => S.checks[`${l.id}:${i}`]).length;
    const pct = Math.round(hechos / l.items.length * 100);
    return `
      <div class="sec-t">${l.icon} ${esc(l.titulo)}</div>
      <div class="card">
        <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--tx3);font-weight:600">
          <span>${hechos} de ${l.items.length}</span><span>${pct}%</span>
        </div>
        <div class="prog"><i style="width:${pct}%"></i></div>
        ${l.items.map((it, i) => {
          const k = `${l.id}:${i}`;
          return `<div class="chk${S.checks[k] ? ' done' : ''}" data-k="${k}">
            <div class="box">${TICK}</div><div class="lb">${esc(it)}</div>
          </div>`;
        }).join('')}
      </div>`;
  }).join('');
}

/* ================= GASTOS ================= */
const fmt = (n, c) => (c === 'MXN' ? '$' : '$') + n.toLocaleString('es-MX', { maximumFractionDigits: 0 });
function pintaGastos() {
  const tc = Number(S.tc) || TRIP.tipoCambioDefault;
  const tot = S.gastos.reduce((a, g) => a + g.m, 0);
  $('#totUsd').textContent = fmt(tot);
  $('#totMxn').textContent = fmt(tot * tc);
  $('#gTc').value = tc;

  const porCat = {};
  S.gastos.forEach(g => { porCat[g.c] = (porCat[g.c] || 0) + g.m; });
  const cats = Object.entries(porCat).sort((a, b) => b[1] - a[1]);
  $('#gPorCat').innerHTML = cats.length
    ? cats.map(([c, m]) => `
        <div style="margin-bottom:11px">
          <div style="display:flex;justify-content:space-between;font-size:13.5px;margin-bottom:5px">
            <span>${esc(c)}</span><b style="font-variant-numeric:tabular-nums">${fmt(m)}</b>
          </div>
          <div class="prog" style="margin:0"><i style="width:${tot ? m / tot * 100 : 0}%"></i></div>
        </div>`).join('')
    : '<p>Todavía no registras gastos.</p>';

  $('#gLista').innerHTML = S.gastos.length
    ? S.gastos.slice().reverse().map(g => `
        <div class="gasto">
          <div style="flex:1;min-width:0">
            <div class="g1">${esc(g.d)}</div>
            <div class="g2">${esc(g.c)} · ${esc(g.f)}</div>
          </div>
          <b>${fmt(g.m)}</b>
          <button class="del" data-del="${g.id}" aria-label="Borrar">&times;</button>
        </div>`).join('')
    : '<p>Sin movimientos.</p>';
}

/* ================= INFO ================= */
const REGLAS = [
  'Cualquier hora marcada con ⏰ en la app es un candado: si se pasa, algo más se cae.',
  'Come en los parques antes de las 12:00 o después de las 14:00. Nunca en medio.',
  'Escanea tu Lightning Lane en cuanto abra la ventana: eso desbloquea la siguiente de inmediato.',
  'Llegar al estacionamiento a la hora de apertura es llegar al parque 40 minutos tarde.',
  'Nunca dejes maletas ni bolsas de compras a la vista dentro del carro.',
  'Confirma horarios de shows en la app oficial el mismo día: cambian y se cancelan por viento.',
  'El día del regreso se planea al revés, desde la hora del vuelo, con 4 horas de colchón.',
  'California va una hora atrás que CDMX durante todo el viaje.'
];
function pintaInfo() {
  $('#tLLfuera').innerHTML =
    '<h3>Lo que tu Lightning Lane NO cubre</h3>' +
    '<p style="margin-top:6px">Son Single Pass: se compran aparte y por atracción. Salvo que lo suyo sea Premier Pass, que sí las incluye.</p>' +
    '<ul class="bullets no" style="margin-top:10px">' +
    LIGHTNING_LANE.fuera.map(x => `<li>${esc(x)}</li>`).join('') + '</ul>';

  $('#tLLreglas').innerHTML = LIGHTNING_LANE.reglas.map(r => `
    <div class="card">
      <h3 style="font-size:15px">${esc(r.t)}</h3>
      <p style="margin-top:5px">${esc(r.d)}</p>
    </div>`).join('');

  $('#tLLorden').innerHTML = LIGHTNING_LANE.orden.map(x => `<li>${esc(x)}</li>`).join('');

  $('#tTraslados').innerHTML = TRASLADOS.map(t => `
    <tr><td>
      <div class="ruta">${esc(t.de)} → ${esc(t.a)}</div>
      <div class="meta">${esc(t.km)} · ${esc(t.nota)}</div>
    </td><td class="tt">${esc(t.tiempo)}</td></tr>`).join('');
  $('#tReglas').innerHTML = REGLAS.map(r => `<li>${esc(r)}</li>`).join('');
  $('#tFuentes').innerHTML = FUENTES.map(f =>
    `<div style="padding:9px 0;border-bottom:1px solid var(--line-soft)">
       <a href="${esc(f.u)}" target="_blank" rel="noopener" style="font-size:13.5px">${esc(f.t)}</a>
     </div>`).join('') +
    '<p style="margin-top:12px;font-size:12.5px">Los horarios de parques, precios y calendarios cambian. Verifica siempre en la app oficial antes de cada día.</p>';
  $('#tNota').innerHTML = 'Viaje SoCal 2026 · Funciona sin conexión una vez que la abres la primera vez. ' +
    'Para instalarla: en iPhone, Compartir → Agregar a inicio. En Android, menú → Instalar aplicación.';
}

/* ================= NAVEGACIÓN ================= */
function ir(v) {
  $$('.view').forEach(s => s.classList.toggle('on', s.id === 'v-' + v));
  $$('#nav button').forEach(b => b.classList.toggle('on', b.dataset.v === v));
  window.scrollTo(0, 0);
}

/* ================= EVENTOS ================= */
document.addEventListener('click', e => {
  const t = e.target;

  const nav = t.closest('#nav button');
  if (nav) return ir(nav.dataset.v);

  const dchip = t.closest('.dchip');
  if (dchip) { S.dia = +dchip.dataset.d; save(); pintaDias(); pintaDia(); return; }

  const goto = t.closest('[data-goto]');
  if (goto) { S.dia = +goto.dataset.goto; save(); pintaDias(); pintaDia(); ir('ruta'); return; }

  const toPark = t.closest('[data-park]');
  if (toPark) { parkId = toPark.dataset.park; pintaParkSel(); pintaPark(); ir('parques'); return; }

  const pchip = t.closest('.pchip');
  if (pchip) { parkId = pchip.dataset.p; pintaParkSel(); pintaPark(); return; }

  const chk = t.closest('.chk');
  if (chk) {
    const k = chk.dataset.k;
    S.checks[k] = !S.checks[k];
    save(); pintaListas(); return;
  }

  const del = t.closest('[data-del]');
  if (del) { S.gastos = S.gastos.filter(g => g.id !== del.dataset.del); save(); pintaGastos(); return; }

  if (t.id === 'gAdd') {
    const d = $('#gDesc').value.trim();
    const m = parseFloat($('#gMonto').value);
    if (!d || !(m > 0)) return;
    const f = new Date();
    S.gastos.push({
      id: String(Date.now()), d, m, c: $('#gCat').value,
      f: `${f.getDate()} ${MES[f.getMonth()]}`
    });
    $('#gDesc').value = ''; $('#gMonto').value = '';
    save(); pintaGastos(); return;
  }

  if (t.id === 'btnExport') {
    const blob = new Blob([JSON.stringify(S, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'viaje-socal-2026-respaldo.json';
    a.click(); URL.revokeObjectURL(a.href); return;
  }

  if (t.id === 'btnReset') {
    if (confirm('¿Borrar tus listas marcadas y todos los gastos? No se puede deshacer.')) {
      S.checks = {}; S.gastos = []; save(); pintaListas(); pintaGastos();
    }
  }
});

$('#gTc').addEventListener('input', e => {
  S.tc = parseFloat(e.target.value) || TRIP.tipoCambioDefault;
  save(); pintaGastos();
});

/* ================= ARRANQUE ================= */
$('#gCat').innerHTML = CATEGORIAS_GASTO.map(c => `<option>${esc(c)}</option>`).join('');
if (S.dia === null || S.dia === undefined) {
  const i = diaActual();
  S.dia = i >= 0 ? i : 0;
}
pintaCuenta(); pintaHoy(); pintaDias(); pintaDia();
pintaParkSel(); pintaPark(); pintaListas(); pintaGastos(); pintaInfo();
setInterval(pintaCuenta, 1000);

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
})();
