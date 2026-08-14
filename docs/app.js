/* ==========================================================================
   Cerebro Liga MX 2026 — render de jornadas
   Este archivo NO calcula probabilidades: sólo formatea lo que el Cerebro
   (Python) ya calculó. La fuente de verdad es el modelo.
   ========================================================================== */

const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const MESES = ["ene", "feb", "mar", "abr", "may", "jun",
               "jul", "ago", "sep", "oct", "nov", "dic"];

const pct = (p, d = 1) => (p * 100).toFixed(d) + "%";

function fecha(iso) {
  const [a, m, d] = iso.split("-").map(Number);
  return `${DIAS[new Date(Date.UTC(a, m - 1, d)).getUTCDay()]} ${d} ${MESES[m - 1]}`;
}

const el = (tag, clase, texto) => {
  const n = document.createElement(tag);
  if (clase) n.className = clase;
  if (texto != null) n.textContent = texto;
  return n;
};
const vaciar = (n) => { while (n.firstChild) n.removeChild(n.firstChild); };

const ORIGEN = {
  publicado: ["Pronóstico sellado antes de jugarse", "sello--ok"],
  reconstruido: ["Reconstruido fuera de muestra", "sello--aviso"],
  vigente: ["Por jugarse", "sello--vivo"],
};

/* ------------------------------------------------------------------ barra */

function barra1x2(p, ocurrio) {
  const barra = el("div", "barra");
  barra.setAttribute("role", "img");
  barra.setAttribute("aria-label",
    `Local ${pct(p.local)}, empate ${pct(p.empate)}, visita ${pct(p.visita)}`);
  [["local", p.local], ["empate", p.empate], ["visita", p.visita]].forEach(([k, v]) => {
    const s = el("div", `barra__seg barra__seg--${k}`);
    s.style.flex = `${v} 1 0`;
    if (k === ocurrio) s.classList.add("barra__seg--ocurrio");
    if (v >= 0.16) s.textContent = pct(v, 0);
    barra.appendChild(s);
  });
  return barra;
}

/* --------------------------------------------------------------- partidos */

function tarjetaPartido(p) {
  const r = p.resultado;
  const ocurrio = r ? (r.gana === "Empate" ? "empate"
                                           : (r.gana === p.local ? "local" : "visita")) : null;

  const card = el("article",
    "partido " + (r ? (r.acerto_1x2 ? "partido--acierto" : "partido--falla")
                    : "partido--pendiente"));
  const cuerpo = el("div", "partido__cuerpo");

  const meta = el("div", "partido__meta");
  meta.append(el("span", null, fecha(p.fecha)), el("span", "partido__estadio", p.estadio));
  cuerpo.appendChild(meta);

  const m = el("div", "marcador");
  const eq = el("div", "marcador__equipos");
  eq.append(document.createTextNode(p.local));
  eq.appendChild(el("div", "marcador__vs", "vs"));
  eq.append(document.createTextNode(p.visitante));
  m.appendChild(eq);
  if (r) {
    m.appendChild(el("div", "marcador__cifras", `${r.gl} – ${r.gv}`));
  } else {
    const pron = el("div", "marcador__pron");
    pron.appendChild(el("span", "marcador__pron-et", "pronóstico"));
    pron.appendChild(el("span", "marcador__pron-num", p.marcador_probable));
    m.appendChild(pron);
  }
  cuerpo.appendChild(m);

  cuerpo.appendChild(barra1x2(p.prob, ocurrio));

  const leyenda = el("div", "leyenda");
  [["local", p.local, p.prob.local], ["empate", "Empate", p.prob.empate],
   ["visita", p.visitante, p.prob.visita]].forEach(([k, nombre, v]) => {
    const s = el("span");
    s.appendChild(el("i", `punto punto--${k}`));
    s.append(document.createTextNode(`${nombre} ${pct(v)}`));
    leyenda.appendChild(s);
  });
  cuerpo.appendChild(leyenda);

  const ver = el("div", "veredicto");
  const pick = el("span");
  pick.append(document.createTextNode("Pick: "));
  pick.appendChild(el("b", null, p.pick));
  if (r) {
    pick.append(document.createTextNode(" "));
    pick.appendChild(el("span", `marca marca--${r.acerto_1x2 ? "si" : "no"}`,
                        r.acerto_1x2 ? "✓" : "✗"));
  }
  ver.appendChild(pick);

  const mar = el("span");
  mar.append(document.createTextNode("Marcador: "));
  mar.appendChild(el("b", null, p.marcador_probable));
  if (r) {
    mar.append(document.createTextNode(" "));
    mar.appendChild(el("span", `marca marca--${r.acerto_marcador ? "si" : "no"}`,
                       r.acerto_marcador ? "✓" : "✗"));
  }
  ver.appendChild(mar);
  if (r) ver.appendChild(el("span", null, `Brier ${r.brier.toFixed(3)}`));
  cuerpo.appendChild(ver);

  if (p.incertidumbre) cuerpo.appendChild(el("p", "aviso", "⚠ " + p.incertidumbre));

  card.appendChild(cuerpo);

  const det = el("details");
  det.appendChild(el("summary", null, "Por qué el modelo dice esto"));
  const cont = el("div", "detalle");
  const capas = el("div", "capas");
  p.bitacora.forEach((b) => {
    const c = el("div", "capa");
    c.appendChild(el("div", "capa__nombre", b.capa));
    c.appendChild(el("div", "capa__lam", `λ ${b.lam[0].toFixed(2)} · ${b.lam[1].toFixed(2)}`));
    c.appendChild(el("div", "capa__detalle", b.detalle));
    capas.appendChild(c);
  });
  cont.appendChild(capas);
  const marc = el("div", "marcadores");
  p.top_marcadores.forEach((t) => {
    const chip = el("span", "chip");
    chip.appendChild(el("b", null, t.marcador));
    chip.append(document.createTextNode(" " + pct(t.prob)));
    marc.appendChild(chip);
  });
  cont.appendChild(marc);
  det.appendChild(cont);
  card.appendChild(det);
  return card;
}

/* ---------------------------------------------------------------- parlays */

const ICONO = { acierto: "✓", falla: "✗", sin_dato: "–", pendiente: "•" };

function tarjetaParlay(p) {
  const card = el("div", "parlay");
  const cabeza = el("div", "parlay__cabeza");
  cabeza.appendChild(el("span", "parlay__nombre", p.nombre));
  cabeza.appendChild(el("span", "parlay__estado",
    p.pego === false ? "No pegó" : (p.pego ? "Pegó" : "Por jugarse")));
  card.appendChild(cabeza);
  card.appendChild(el("p", "parlay__desc", p.descripcion));

  const lista = el("ul", "legs");
  p.legs.forEach((l) => {
    const li = el("li", "leg");
    li.appendChild(el("span", `leg__icono leg__icono--${l.estado}`, ICONO[l.estado]));
    li.appendChild(el("span", null, l.etiqueta));
    li.appendChild(el("span", "leg__prob", pct(l.prob)));
    li.appendChild(el("span", "leg__partido",
      l.estado === "sin_dato" ? `${l.partido} · sin marcador de medio tiempo` : l.partido));
    lista.appendChild(li);
  });
  card.appendChild(lista);

  const pie = el("div", "parlay__pie");
  pie.appendChild(el("span", null, `${p.legs.length} picks`));
  const pr = el("span");
  pr.append(document.createTextNode("Prob. combinada "));
  pr.appendChild(el("b", null, pct(p.prob_conjunta)));
  pie.appendChild(pr);
  card.appendChild(pie);
  return card;
}

/* ------------------------------------------------------------------ render */

function pintaJornada(d) {
  document.getElementById("titulo").textContent = `Jornada ${d.jornada}`;
  document.getElementById("subtitulo").textContent = d.torneo;

  const [txt, clase] = ORIGEN[d.origen] || ORIGEN.vigente;
  const sello = document.getElementById("sello");
  sello.textContent = txt;
  sello.className = "sello " + clase;

  const notaOrigen = document.getElementById("nota-origen");
  notaOrigen.textContent = d.nota_origen || "";
  notaOrigen.hidden = !d.nota_origen;

  /* resumen de la jornada */
  const res = document.getElementById("resumen");
  vaciar(res);
  const tituloRes = document.getElementById("titulo-resumen");
  if (d.resumen) {
    tituloRes.textContent = "Cómo le fue al modelo";
    const j = d.resumen, malo = j.brier > 0.667;
    [["Aciertos 1X2", `${j.aciertos_1x2}/${j.partidos}`,
      pct(j.aciertos_1x2 / j.partidos, 0), false],
     ["Marcador exacto", `${j.marcadores_exactos}/${j.partidos}`, "de 9 partidos", false],
     ["Brier", j.brier.toFixed(3),
      malo ? "peor que el azar (0.667)" : "mejor que el azar (0.667)", malo],
     ["Parlays", `${j.parlays_pegados}/3`,
      j.parlays_pegados ? "" : "ninguno pegó", j.parlays_pegados === 0],
    ].forEach(([et, val, nota, m]) => {
      const c = el("div", "dato" + (m ? " dato--malo" : ""));
      c.appendChild(el("div", "dato__etiqueta", et));
      c.appendChild(el("div", "dato__valor", val));
      c.appendChild(el("div", "dato__nota", nota));
      res.appendChild(c);
    });
  } else {
    tituloRes.textContent = "Jornada por jugarse";
    const h = d.modelo.historico;
    [["Partidos", String(d.partidos.length), "aún sin resultado", false],
     ["Calibrado con", h.partidos.toLocaleString("es-MX"), `partidos, hasta ${fecha(h.hasta)}`, false],
     ["Corte", fecha(d.corte_calibracion), "no ve nada posterior", true],
    ].forEach(([et, val, nota, texto]) => {
      const c = el("div", "dato" + (texto ? " dato--texto" : ""));
      c.appendChild(el("div", "dato__etiqueta", et));
      c.appendChild(el("div", "dato__valor", val));
      c.appendChild(el("div", "dato__nota", nota));
      res.appendChild(c);
    });
  }

  const partidos = document.getElementById("partidos");
  vaciar(partidos);
  d.partidos.forEach((p) => partidos.appendChild(tarjetaPartido(p)));

  const parlays = document.getElementById("parlays");
  vaciar(parlays);
  ["recomendado", "seguro", "agresivo"].forEach((k) => {
    if (d.parlays[k]) parlays.appendChild(tarjetaParlay(d.parlays[k]));
  });

  /* procedencia */
  const h = d.modelo.historico, cr = d.modelo.credibilidad || {};
  document.getElementById("procedencia").innerHTML =
    `Dixon-Coles con corrección ρ = ${d.modelo.rho_dc} sobre la malla exacta de marcadores. ` +
    `Calibrado por máxima verosimilitud con <b>${h.partidos.toLocaleString("es-MX")} partidos reales</b> ` +
    `(${h.desde} a ${h.hasta}), decaimiento temporal ξ = ${d.modelo.xi_decaimiento} por día. ` +
    `Corte de calibración: <b>${d.corte_calibracion}</b> — el modelo no ve ningún partido posterior. ` +
    (cr.activa ? `Credibilidad Z = w³/(w³+${cr.k}³) hacia el prior para equipos con poco histórico. ` : "") +
    `Mitades por adelgazamiento de Poisson con ${pct(d.modelo.prop_goles_1t, 2)} de los goles en el 1T.`;
  document.getElementById("nomodelado").textContent = d.no_modelado.join(", ");
}

function pintaIndice(idx, actual, alCambiar) {
  const nav = document.getElementById("jornadas");
  vaciar(nav);
  idx.jornadas.forEach((j) => {
    const b = el("button", "tab" + (j.jornada === actual ? " tab--activa" : ""),
                 `J${j.jornada}`);
    b.type = "button";
    b.setAttribute("aria-pressed", String(j.jornada === actual));
    if (j.estado === "vigente") b.appendChild(el("i", "tab__vivo"));
    b.addEventListener("click", () => alCambiar(j.jornada));
    nav.appendChild(b);
  });

  const tb = document.getElementById("historico");
  vaciar(tb);
  idx.desempeno.por_jornada.forEach((h) => {
    const tr = document.createElement("tr");
    const et = `Jornada ${h.jornada}` + (h.origen === "reconstruido" ? " *" : "");
    [et, `${h.aciertos_1x2}/${h.partidos}`, String(h.marcadores_exactos),
     h.brier.toFixed(3)].forEach((t) => {
      const td = document.createElement("td");
      td.textContent = t;
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
  const a = idx.desempeno.acumulado;
  const tr = document.createElement("tr");
  tr.className = "acumulado";
  ["Acumulado", `${a.aciertos_1x2}/${a.partidos}`, String(a.marcadores_exactos),
   a.brier.toFixed(3)].forEach((t) => {
    const td = document.createElement("td");
    td.textContent = t;
    tr.appendChild(td);
  });
  tb.appendChild(tr);

  document.getElementById("convencion").textContent = idx.desempeno.convencion_brier;
}

/* ------------------------------------------------------------------ arranque */

function iniciar(idx, cargar) {
  let actual = idx.jornada_vigente;

  const ir = (n) => {
    actual = n;
    pintaIndice(idx, actual, ir);
    Promise.resolve(cargar(n)).then((d) => {
      pintaJornada(d);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  };
  ir(actual);
}

if (typeof DATOS !== "undefined") {
  /* vista previa de un solo archivo: todo viene embebido */
  iniciar(DATOS.indice, (n) => DATOS.jornadas[String(n)]);
} else {
  fetch("datos/indice.json", { cache: "no-cache" })
    .then((r) => r.json())
    .then((idx) => iniciar(idx, (n) =>
      fetch(`datos/j${String(n).padStart(2, "0")}.json`).then((r) => r.json())))
    .catch(() => {
      document.getElementById("resumen").textContent =
        "No se pudieron cargar las jornadas. Recarga la página.";
    });
}
