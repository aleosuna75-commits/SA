/* ==========================================================================
   Cerebro Liga MX 2026 — render de la jornada
   Este archivo NO calcula probabilidades: sólo formatea lo que el Cerebro
   (Python) ya calculó. La fuente de verdad es el modelo.
   ========================================================================== */

const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const MESES = ["ene", "feb", "mar", "abr", "may", "jun",
               "jul", "ago", "sep", "oct", "nov", "dic"];

const pct = (p, d = 1) => (p * 100).toFixed(d) + "%";

function fecha(iso) {
  const [a, m, d] = iso.split("-").map(Number);
  const f = new Date(Date.UTC(a, m - 1, d));
  return `${DIAS[f.getUTCDay()]} ${d} ${MESES[m - 1]}`;
}

const el = (tag, clase, texto) => {
  const n = document.createElement(tag);
  if (clase) n.className = clase;
  if (texto != null) n.textContent = texto;
  return n;
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
  const ocurrio = r.gana === "Empate" ? "empate" : (r.gana === p.local ? "local" : "visita");

  const card = el("article", `partido partido--${r.acerto_1x2 ? "acierto" : "falla"}`);
  const cuerpo = el("div", "partido__cuerpo");

  const meta = el("div", "partido__meta");
  meta.append(el("span", null, fecha(p.fecha)),
              el("span", "partido__estadio", p.estadio));
  cuerpo.appendChild(meta);

  const m = el("div", "marcador");
  const eq = el("div", "marcador__equipos");
  eq.append(document.createTextNode(p.local));
  eq.appendChild(el("div", "marcador__vs", "vs"));
  eq.append(document.createTextNode(p.visitante));
  m.appendChild(eq);
  m.appendChild(el("div", "marcador__cifras", `${r.gl} – ${r.gv}`));
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
  pick.append(document.createTextNode(" "));
  pick.appendChild(el("span", `marca marca--${r.acerto_1x2 ? "si" : "no"}`,
                      r.acerto_1x2 ? "✓" : "✗"));
  const mar = el("span");
  mar.append(document.createTextNode("Marcador: "));
  mar.appendChild(el("b", null, p.marcador_probable));
  mar.append(document.createTextNode(" "));
  mar.appendChild(el("span", `marca marca--${r.acerto_marcador ? "si" : "no"}`,
                     r.acerto_marcador ? "✓" : "✗"));
  ver.append(pick, mar, el("span", null, `Brier ${r.brier.toFixed(3)}`));
  cuerpo.appendChild(ver);

  card.appendChild(cuerpo);

  /* --- desplegable: la bitácora --- */
  const det = el("details");
  det.appendChild(el("summary", null, "Por qué el modelo dijo esto"));
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

const ICONO = { acierto: "✓", falla: "✗", sin_dato: "–" };

function tarjetaParlay(p) {
  const card = el("div", "parlay");

  const cabeza = el("div", "parlay__cabeza");
  cabeza.appendChild(el("span", "parlay__nombre", p.nombre));
  cabeza.appendChild(el("span", "parlay__estado",
    p.pego === false ? "No pegó" : (p.pego ? "Pegó" : "Sin resolver")));
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

function render(d) {
  const j = d.desempeno.jornada;

  document.getElementById("titulo").textContent = `Jornada ${d.jornada}`;
  document.getElementById("subtitulo").textContent = d.torneo;

  /* tarjetas de resumen */
  const res = document.getElementById("resumen");
  const brierMalo = j.brier > 0.667;
  [
    ["Aciertos 1X2", `${j.aciertos_1x2}/${j.partidos}`, pct(j.aciertos_1x2 / j.partidos, 0), false],
    ["Marcador exacto", `${j.marcadores_exactos}/${j.partidos}`, "de 9 partidos", false],
    ["Brier", j.brier.toFixed(3), brierMalo ? "peor que el azar (0.667)" : "mejor que el azar (0.667)", brierMalo],
    ["Parlays", `${j.parlays_pegados}/3`, "ninguno pegó", true],
  ].forEach(([et, val, nota, malo]) => {
    const c = el("div", "dato" + (malo ? " dato--malo" : ""));
    c.appendChild(el("div", "dato__etiqueta", et));
    c.appendChild(el("div", "dato__valor", val));
    c.appendChild(el("div", "dato__nota", nota));
    res.appendChild(c);
  });

  const partidos = document.getElementById("partidos");
  d.partidos.forEach((p) => partidos.appendChild(tarjetaPartido(p)));

  const parlays = document.getElementById("parlays");
  ["recomendado", "seguro", "agresivo"].forEach((k) => {
    if (d.parlays[k]) parlays.appendChild(tarjetaParlay(d.parlays[k]));
  });

  /* histórico por jornada */
  const tb = document.getElementById("historico");
  let ac = 0, pj = 0, ex = 0, sb = 0;
  d.desempeno.historico.forEach((h) => {
    ac += h.aciertos_1x2; pj += h.partidos; ex += h.marcadores_exactos; sb += h.brier;
    const tr = document.createElement("tr");
    [`Jornada ${h.jornada}`, `${h.aciertos_1x2}/${h.partidos}`,
     String(h.marcadores_exactos), h.brier.toFixed(3)].forEach((t) => {
      const td = document.createElement("td");
      td.textContent = t;
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
  const tr = document.createElement("tr");
  tr.className = "acumulado";
  [`Acumulado`, `${ac}/${pj}`, String(ex),
   (sb / d.desempeno.historico.length).toFixed(3)].forEach((t) => {
    const td = document.createElement("td");
    td.textContent = t;
    tr.appendChild(td);
  });
  tb.appendChild(tr);

  document.getElementById("convencion").textContent = d.desempeno.convencion_brier;

  /* procedencia */
  const h = d.modelo.historico;
  document.getElementById("procedencia").innerHTML =
    `Dixon-Coles con corrección ρ = ${d.modelo.rho_dc} y ${d.modelo.simulaciones.toLocaleString("es-MX")} ` +
    `simulaciones Monte Carlo por partido. Calibrado por máxima verosimilitud sobre ` +
    `<b>${h.partidos.toLocaleString("es-MX")} partidos reales</b> (${h.desde} a ${h.hasta}), ` +
    `con decaimiento temporal ξ = ${d.modelo.xi_decaimiento} por día. ` +
    `Mitades por adelgazamiento de Poisson con ${pct(d.modelo.prop_goles_1t, 2)} de los goles en el 1T.`;
  document.getElementById("huella").textContent = h.sha256;
  document.getElementById("nomodelado").textContent = d.no_modelado.join(", ");
}

/* Los datos vienen embebidos (vista previa) o del JSON de la jornada. */
if (typeof DATOS !== "undefined") {
  render(DATOS);
} else {
  fetch("datos/j02.json", { cache: "no-cache" })
    .then((r) => r.json())
    .then(render)
    .catch(() => {
      document.getElementById("resumen").textContent =
        "No se pudo cargar la jornada. Recarga la página.";
    });
}
