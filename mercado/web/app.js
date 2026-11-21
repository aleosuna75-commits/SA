/* Mercado: todo se calcula en el navegador a partir de datos/*.json (ver mercado/pipeline.py) */
(async function () {
  const [meta, crudos, clubes, mundo] = await Promise.all(
    ["datos/meta.json", "datos/jugadores.json", "datos/clubes.json", "lib/countries-50m.json"]
      .map((u) => fetch(u).then((r) => r.json())));

  // ================================================================ catálogos
  const POS = ["Portero", "Defensa", "Medio", "Delantero"], POS_C = ["POR", "DEF", "MED", "DEL"];
  const SUBPOS = { "Attacking Midfield": "Mediapunta", "Central Midfield": "Medio centro", "Centre-Back": "Central",
    "Centre-Forward": "Delantero centro", "Defensive Midfield": "Pivote", Goalkeeper: "Portero", "Left Midfield": "Interior izquierdo",
    "Left Winger": "Extremo izquierdo", "Left-Back": "Lateral izquierdo", "Right Midfield": "Interior derecho",
    "Right Winger": "Extremo derecho", "Right-Back": "Lateral derecho", "Second Striker": "Segundo delantero" };
  const PIE = ["Derecho", "Zurdo", "Ambidiestro"];
  const ETQ = [["Estrella", 60e6], ["Élite", 25e6], ["Cumplidor", 8e6], ["Regular", 2e6], ["De rol", 0]];
  const SENAL = [["Al alza", "sube"], ["Estable", "plano"], ["A la baja", "baja"]];
  const NIVEL = { 0: "Sin club", 1: "1ª división", 2: "2ª división", 3: "3ª división", 4: "4ª división", 5: "5ª o inferior", 9: "Sin identificar" };
  const ES = { Germany: "Alemania", "Saudi Arabia": "Arabia Saudita", Algeria: "Argelia", Belgium: "Bélgica", Belarus: "Bielorrusia",
    "Bosnia-Herzegovina": "Bosnia y Herzegovina", Brazil: "Brasil", Cambodia: "Camboya", Canada: "Canadá", "Czech Republic": "Chequia",
    "Chinese Taipei": "Taiwán", "Korea, South": "Corea del Sur", Croatia: "Croacia", Denmark: "Dinamarca", Egypt: "Egipto",
    "United Arab Emirates": "Emiratos Árabes", Scotland: "Escocia", Slovakia: "Eslovaquia", Slovenia: "Eslovenia", Spain: "España",
    "United States": "Estados Unidos", Ethiopia: "Etiopía", Finland: "Finlandia", France: "Francia", Wales: "Gales", Greece: "Grecia",
    Hongkong: "Hong Kong", Hungary: "Hungría", England: "Inglaterra", Iran: "Irán", Ireland: "Irlanda", "Northern Ireland": "Irlanda del Norte",
    Iceland: "Islandia", "Faroe Islands": "Islas Feroe", Italy: "Italia", Japan: "Japón", Jordan: "Jordania", Kazakhstan: "Kazajistán",
    Kyrgyzstan: "Kirguistán", Latvia: "Letonia", Lebanon: "Líbano", Libya: "Libia", Lithuania: "Lituania", Luxembourg: "Luxemburgo",
    "North Macedonia": "Macedonia del Norte", Malaysia: "Malasia", Morocco: "Marruecos", Mexico: "México", Moldova: "Moldavia",
    Norway: "Noruega", Netherlands: "Países Bajos", Panama: "Panamá", Peru: "Perú", Poland: "Polonia", "Dominican Republic": "Rep. Dominicana",
    Romania: "Rumania", Russia: "Rusia", "South Africa": "Sudáfrica", Sweden: "Suecia", Switzerland: "Suiza", Thailand: "Tailandia",
    Tajikistan: "Tayikistán", Tunisia: "Túnez", "Türkiye": "Turquía", Ukraine: "Ucrania", Uzbekistan: "Uzbekistán", Singapore: "Singapur" };
  const EN_MAPA = { England: "United Kingdom", Scotland: "United Kingdom", Wales: "United Kingdom", "Northern Ireland": "United Kingdom",
    "United States": "United States of America", "Korea, South": "South Korea", "Türkiye": "Turkey", "Czech Republic": "Czechia",
    "Bosnia-Herzegovina": "Bosnia and Herz.", "Dominican Republic": "Dominican Rep.", "North Macedonia": "Macedonia",
    "Chinese Taipei": "Taiwan", Hongkong: "Hong Kong", "Faroe Islands": "Faeroe Is." };
  const AMERICA = "Argentina,Bolivia,Brazil,Canada,Chile,Colombia,Costa Rica,Dominican Republic,Ecuador,El Salvador,Guatemala,Honduras,Jamaica,Mexico,Panama,Paraguay,Peru,Puerto Rico,United States,Uruguay,Venezuela".split(",");
  const AFRICA = "Algeria,Egypt,Ethiopia,Libya,Morocco,Nigeria,Senegal,South Africa,Tunisia,Uganda".split(",");
  const ASIA = "Australia,Bangladesh,Cambodia,China,Chinese Taipei,Hongkong,India,Indonesia,Iran,Iraq,Japan,Jordan,Korea, South,Kyrgyzstan,Laos,Lebanon,Malaysia,Myanmar,Oman,Qatar,Saudi Arabia,Singapore,Tajikistan,Thailand,United Arab Emirates,Uzbekistan,Vietnam".split(/,(?! )/);
  const region = (p) => !p ? "" : AMERICA.includes(p) ? "América" : AFRICA.includes(p) ? "África" : ASIA.includes(p) ? "Asia y Oceanía" : "Europa";
  const enMapa = (p) => EN_MAPA[p] || p;
  const es = (p) => ES[p] || p;

  // ================================================================ utilidades
  const $ = (s, r = document) => r.querySelector(s);
  const sinAcentos = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function eur(v) {
    if (v == null || !isFinite(v)) return "—";
    const a = Math.abs(v), s = v < 0 ? "−" : "";
    if (a >= 1e9) return s + "€" + (a / 1e9).toFixed(2) + "B";
    if (a >= 1e6) return s + "€" + (a / 1e6).toFixed(a >= 1e7 ? 0 : 1) + "M";
    if (a >= 1e3) return s + "€" + Math.round(a / 1e3) + "k";
    return s + "€" + Math.round(a);
  }
  const pct = (x) => (x == null || !isFinite(x) ? "—" : (x >= 0 ? "+" : "−") + Math.abs(Math.round(x * 100)) + "%");
  const tono = (x) => (x == null ? "plano" : x > 0.03 ? "sube" : x < -0.03 ? "baja" : "plano");
  const mil = (n) => n.toLocaleString("es-MX");
  const MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const fechaYM = (ym) => `${MES[(ym % 100) - 1]} ${Math.floor(ym / 100)}`;
  const corteYM = +meta.corte.slice(0, 4) * 100 + +meta.corte.slice(5, 7);
  const anioDec = (ym) => Math.floor(ym / 100) + ((ym % 100) - 0.5) / 12;
  const IM = meta.indice_mercado, i19 = IM.anios.indexOf(2019);
  const INFL_RECIENTE = Math.pow(IM.valor.at(-1) / IM.valor[i19], 1 / (IM.anios.at(-1) - 2019)) - 1;   // ritmo desde 2019
  const eq = (n) => `${n} equipo${n === 1 ? "" : "s"}`;

  // ================================================================ jugadores (las proyecciones vienen calculadas del pipeline)
  const club = new Map(clubes.map((c) => [c.id, c]));
  const HK = [1, 2, 3, 5, 8];                               // horizontes con mediana en la fila; la curva completa va en el detalle
  const nulo = (v) => (v < 0 ? null : v);
  function med(j, h) {                                      // mediana a h años interpolando entre los horizontes de la fila
    const pts = [[0, j.valor]].concat(HK.map((k, i) => [k, j.V[i]]).filter((p) => p[1] != null));
    if (h > pts[pts.length - 1][0]) return null;
    for (let i = 1; i < pts.length; i++) if (h <= pts[i][0]) return pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * (h - pts[i - 1][0]) / (pts[i][0] - pts[i - 1][0]);
    return null;
  }
  const jugadores = crudos.map((r) => {
    const j = { id: r[0], nombre: r[1], club: r[2], pos: r[3], subpos: r[4], edad: r[5], nac: r[6], valor: r[7], maxHist: r[8],
      pj: r[9], min: r[10], goles: r[11], asist: r[12], contrato: r[13], fecha: r[14], pie: r[15], altura: r[16], les24: r[17], cedido: r[18],
      pLo95: r[30], pLo: r[31], precio: r[32], pHi: r[33], pHi95: r[34],
      V: [r[19], r[20], r[21], r[22], r[23]].map(nulo), s3: nulo(r[24]), pico: r[25], techo: r[26], edadPico: r[27] || null, cubierta: r[28], H: r[29] };
    const c = club.get(j.club);
    j.c = c; j.pais = c.pais; j.liga = c.liga; j.nivel = c.nivel;
    j.v1 = j.V[0]; j.v3 = j.V[2] ?? j.V[1] ?? j.V[0]; j.v5 = j.V[3] ?? j.v3;
    j.h3 = Math.min(3, j.H) || 1;
    j.prima = j.precio / j.valor - 1;                         // cuánto más (o menos) se paga que su valor de Transfermarkt
    j.r3 = j.v3 != null ? j.v3 / j.valor - 1 : null;
    j.d3 = j.v3 != null ? j.v3 - j.valor : null;
    j.senal = j.r3 == null ? 1 : j.r3 > 0.15 ? 0 : j.r3 < -0.15 ? 2 : 1;
    j.etq = ETQ.findIndex((e) => j.pico >= e[1]);
    j.meses = j.contrato ? (+j.contrato.slice(0, 4) - Math.floor(corteYM / 100)) * 12 + (+j.contrato.slice(5, 7) - (corteYM % 100)) : null;
    j.clave = sinAcentos(j.nombre);
    return j;
  });
  const porId = new Map(jugadores.map((j) => [j.id, j]));
  const RT = meta.retro, mediaDe = (arr, k) => d3.mean(arr, (x) => x[k]);

  // ================================================================ lista de seguimiento
  let lista = new Set();
  try { lista = new Set(JSON.parse(localStorage.getItem("mercado.lista") || "[]")); } catch (e) { /* sin almacenamiento */ }
  function alternarLista(id) {
    lista.has(id) ? lista.delete(id) : lista.add(id);
    try { localStorage.setItem("mercado.lista", JSON.stringify([...lista])); } catch (e) { /* sin almacenamiento */ }
    $("#n-lista").textContent = lista.size || "";
    document.querySelectorAll(`[data-star="${id}"]`).forEach((b) => b.classList.toggle("on", lista.has(id)));
  }
  const estrella = (j) => `<button class="estrella ${lista.has(j.id) ? "on" : ""}" data-star="${j.id}" title="Agregar a mi lista" aria-label="Agregar a mi lista">★</button>`;

  // ================================================================ filtros
  const F0 = { region: "", pais: "", liga: "", nivel: "", pos: "", subpos: "", nac: "", pie: "", emin: 15, emax: 50, vmin: "", vmax: "",
    contrato: "", perfil: "", senal: "" };
  const F = { ...F0 };
  function opciones(id, lista_, vacio) {
    const sel = $(id), actual = sel.value;
    sel.length = 0;
    sel.add(new Option(vacio, ""));
    lista_.forEach(([v, t]) => sel.add(new Option(t, v)));
    sel.value = lista_.some(([v]) => String(v) === actual) ? actual : "";
    return sel.value;
  }
  const paisesLiga = [...new Set(clubes.map((c) => c.pais).filter(Boolean))].sort((a, b) => es(a).localeCompare(es(b)));
  opciones("#f-region", ["América", "Europa", "Asia y Oceanía", "África"].map((r) => [r, r]), "Todas");
  opciones("#f-nivel", Object.entries(NIVEL), "Todas");
  opciones("#f-pos", POS.map((p, i) => [i, p]), "Todas");
  opciones("#f-subpos", meta.subposiciones.map((s, i) => [i, SUBPOS[s] || s]), "Todos");
  opciones("#f-nac", meta.paises.map((p, i) => [i, es(p)]).sort((a, b) => a[1].localeCompare(b[1])), "Todas");
  opciones("#f-pie", PIE.map((p, i) => [i, p]), "Todos");
  opciones("#f-contrato", [[6, "En 6 meses o menos"], [12, "En 12 meses o menos"], [24, "En 24 meses o menos"]], "Cualquiera");
  opciones("#f-perfil", ETQ.map((e, i) => [i, e[0]]), "Todos");
  opciones("#f-senal", SENAL.map((s, i) => [i, s[0]]), "Todas");
  function cascada() {
    F.pais = opciones("#f-pais", paisesLiga.filter((p) => !F.region || region(p) === F.region).map((p) => [p, es(p)]), "Todos");
    const ligas = new Map();
    clubes.forEach((c) => { if (c.nivel >= 1 && c.nivel <= 8 && (!F.region || region(c.pais) === F.region) && (!F.pais || c.pais === F.pais)) ligas.set(c.pais + "|" + c.liga, c); });
    F.liga = opciones("#f-liga", [...ligas.entries()].sort((a, b) => es(a[1].pais).localeCompare(es(b[1].pais)) || a[1].nivel - b[1].nivel)
      .map(([k, c]) => [k, `${es(c.pais)} · ${c.liga}`]), "Todas");
  }
  cascada();
  function pasa(j) {
    return (!F.region || region(j.pais) === F.region) && (!F.pais || j.pais === F.pais) && (!F.liga || j.pais + "|" + j.liga === F.liga)
      && (F.nivel === "" || (+F.nivel === 5 ? j.nivel >= 5 && j.nivel < 9 : j.nivel === +F.nivel))
      && (F.pos === "" || j.pos === +F.pos) && (F.subpos === "" || j.subpos === +F.subpos) && (F.nac === "" || j.nac === +F.nac)
      && (F.pie === "" || j.pie === +F.pie) && j.edad >= F.emin && j.edad <= F.emax
      && (F.vmin === "" || j.valor >= F.vmin * 1e6) && (F.vmax === "" || j.valor <= F.vmax * 1e6)
      && (F.contrato === "" || (j.meses != null && j.meses <= +F.contrato && j.meses >= -2))
      && (F.perfil === "" || j.etq === +F.perfil) && (F.senal === "" || j.senal === +F.senal);
  }
  let filtrados = jugadores;
  function aplicarFiltros() {
    filtrados = jugadores.filter(pasa);
    const activos = Object.keys(F0).filter((k) => String(F[k]) !== String(F0[k])).length;
    $("#resumen-filtros").textContent = `${mil(filtrados.length)} de ${mil(jugadores.length)} jugadores${activos ? ` · ${activos} filtro${activos > 1 ? "s" : ""} activo${activos > 1 ? "s" : ""}` : ""}`;
  }
  function fijarFiltros(cambios) {
    Object.assign(F, F0, cambios);
    Object.keys(F0).forEach((k) => { if (!["pais", "liga"].includes(k)) $("#f-" + k).value = F[k]; });
    const { pais, liga } = F;
    cascada();
    $("#f-pais").value = F.pais = pais; cascada(); $("#f-liga").value = F.liga = liga;
    aplicarFiltros();
  }
  Object.keys(F0).forEach((k) => $("#f-" + k).addEventListener("change", (e) => {
    const v = e.target.value;
    F[k] = ["emin", "emax"].includes(k) ? +v || F0[k] : ["vmin", "vmax"].includes(k) ? (v === "" ? "" : +v) : v;
    if (k === "region" || k === "pais") cascada();
    aplicarFiltros(); pintar();
  }));
  $("#limpiar").onclick = () => { fijarFiltros({}); pintar(); };

  // ================================================================ tabla reutilizable
  const COLS = {
    nombre: ["Jugador", (j) => j.nombre, (j) => `${estrella(j)} <b>${esc(j.nombre)}</b><span class="sub">${esc(j.c.nombre)}${j.cedido ? " · cedido" : ""}</span>`, "izq"],
    pos: ["Pos", (j) => j.pos, (j) => POS_C[j.pos]],
    edad: ["Edad", (j) => j.edad, (j) => j.edad],
    liga: ["Liga", (j) => es(j.pais) + j.liga, (j) => `${esc(j.liga)}<span class="sub">${esc(es(j.pais)) || "—"}</span>`, "izq"],
    valor: ["Valor TM", (j) => j.valor, (j) => eur(j.valor)],
    precio: ["Precio est.", (j) => j.precio, (j) => `${eur(j.precio)}<span class="sub ${tono(j.prima)}">${pct(j.prima)} vs TM</span>`],
    v1: ["1 año", (j) => j.v1 ?? -1, (j) => eur(j.v1)],
    v3: ["3 años", (j) => j.v3 ?? -1, (j) => eur(j.v3)],
    r3: ["Δ 3 años", (j) => j.r3 ?? -9, (j) => `<span class="${tono(j.r3)}">${pct(j.r3)}</span>`],
    d3: ["Δ€ 3 años", (j) => j.d3 ?? 0, (j) => `<span class="${tono(j.r3)}">${eur(j.d3)}</span>`],
    v5: ["5 años", (j) => j.v5 ?? -1, (j) => eur(j.v5)],
    pico: ["Máx. carrera", (j) => j.pico, (j) => eur(j.pico)],
    techo: ["Techo", (j) => j.techo, (j) => eur(j.techo)],
    perfil: ["Perfil", (j) => -j.etq, (j) => `<span class="etq e${j.etq}">${ETQ[j.etq][0]}</span>`],
    contrato: ["Contrato", (j) => j.contrato || "9999", (j) => (j.contrato ? fechaYM(+j.contrato.replace("-", "")) : "—")],
    min: ["Min 12m", (j) => j.min, (j) => (j.min < 0 ? "—" : mil(j.min))],
  };
  const tablas = {};
  function tabla(id, datos, cols, orden = "pico", porPag = 50) {
    const t = tablas[id] = tablas[id] || { orden, asc: false, pag: 0 };
    t.datos = datos; t.cols = cols; t.porPag = porPag;
    return `<div data-tabla="${id}">${cuerpoTabla(id)}</div>`;
  }
  function cuerpoTabla(id) {
    const t = tablas[id], k = COLS[t.orden][1];
    const ord = [...t.datos].sort((a, b) => { const x = k(a), y = k(b); return (x < y ? -1 : x > y ? 1 : 0) * (t.asc ? 1 : -1); });
    const pags = Math.max(1, Math.ceil(ord.length / t.porPag));
    t.pag = Math.min(t.pag, pags - 1);
    const filas = ord.slice(t.pag * t.porPag, (t.pag + 1) * t.porPag);
    return `<div class="tabla-caja"><table><thead><tr>${t.cols.map((c) => `<th data-sort="${c}" class="${COLS[c][3] || ""} ${t.orden === c ? "orden" + (t.asc ? " asc" : "") : ""}">${COLS[c][0]}</th>`).join("")}</tr></thead>
      <tbody>${filas.map((j) => `<tr data-j="${j.id}">${t.cols.map((c) => `<td class="${COLS[c][3] || ""}">${COLS[c][2](j)}</td>`).join("")}</tr>`).join("")
        || `<tr><td class="izq" colspan="${t.cols.length}">Nadie cumple estos criterios.</td></tr>`}</tbody></table></div>
      <div class="pag"><span>${mil(ord.length)} jugadores · página ${t.pag + 1} de ${pags}</span>
        <span><button data-pag="-1" ${t.pag ? "" : "disabled"}>Anterior</button> <button data-pag="1" ${t.pag < pags - 1 ? "" : "disabled"}>Siguiente</button>
        <button data-csv="${id}">Descargar CSV</button></span></div>`;
  }
  function csv(id) {
    const t = tablas[id];
    const cab = ["id", "jugador", "club", "liga", "pais_liga", "division", "posicion", "edad", "valor_tm", "fecha_valor", "precio_estimado", "precio_bajo_95", "precio_alto_95", "mediana_1a", "mediana_3a", "mediana_5a",
      "max_carrera", "techo_p90", "contrato", "minutos_12m"];
    const fila = (j) => [j.id, j.nombre, j.c.nombre, j.liga, j.pais, j.nivel, POS[j.pos], j.edad, j.valor, j.fecha, j.precio, j.pLo95, j.pHi95, j.v1, j.v3, j.v5, j.pico, j.techo, j.contrato, j.min < 0 ? "" : j.min]
      .map((v) => (v == null ? "" : typeof v === "number" ? Math.round(v) : `"${String(v).replace(/"/g, '""')}"`)).join(",");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿" + cab.join(",") + "\n" + t.datos.map(fila).join("\n")], { type: "text/csv" }));
    a.download = `mercado_${id}_${meta.corte}.csv`;
    a.click();
  }
  const filaJ = (j, derecha) => `<div class="fila" data-j="${j.id}"><span class="n">${esc(j.nombre)} <span class="etq e${j.etq}">${ETQ[j.etq][0]}</span></span>
    <span class="s">${POS_C[j.pos]} · ${j.edad} años · ${esc(j.c.nombre)}</span><span class="v">${derecha(j)}</span></div>`;

  // ================================================================ rutas
  let ruta = { v: "mapa", arg: "", j: null };
  function leerRuta() {
    const [camino, qs] = location.hash.replace(/^#\/?/, "").split("?");
    const [v, ...resto] = camino.split("/");
    ruta = { v: v || "mapa", arg: decodeURIComponent(resto.join("/")), j: qs && +new URLSearchParams(qs).get("j") || null };
  }
  const base = () => `#/${ruta.v}${ruta.arg ? "/" + encodeURIComponent(ruta.arg) : ""}`;
  const abrirJ = (id) => { location.hash = `${base()}?j=${id}`; };
  const cerrarJ = () => { location.hash = base(); };
  let previa = "";
  window.addEventListener("hashchange", () => { leerRuta(); const b = base(); if (b !== previa) pintar(); else pintarFicha(); });

  function pintar() {
    previa = base();
    document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("activo", a.dataset.v === ruta.v));
    $("#caja-filtros").hidden = ["metodo", "lista", "club"].includes(ruta.v);
    ({ mapa: vistaMapa, radar: vistaRadar, explorar: vistaExplorar, lista: vistaLista, metodo: vistaMetodo, club: vistaClub }[ruta.v] || vistaMapa)();
    pintarFicha();
    if (ruta.v !== "mapa") scrollTo(0, 0);
  }

  // ================================================================ vista: mapa
  const geo = topojson.feature(mundo, mundo.objects.countries).features.filter((f) => f.properties.name !== "Antarctica");
  const conLiga = new Set(paisesLiga.map(enMapa));
  let M = null;
  function vistaMapa() {
    const v = $("#vista");
    if (!$("#mapa")) {
      v.innerHTML = `<div class="mapa-vista"><section id="mapa"><svg></svg>
        <div class="controles"><button id="z-mas" aria-label="Acercar">+</button><button id="z-menos" aria-label="Alejar">−</button><button id="z-mundo" aria-label="Ver el mundo">⌂</button></div>
        <div class="leyenda">menos valor<i></i>más valor</div></section><aside class="lateral" id="lateral"></aside></div>`;
      const svg = d3.select("#mapa svg"), g = svg.append("g");
      const pr = d3.geoNaturalEarth1(), trazo = d3.geoPath(pr);
      const zoom = d3.zoom().scaleExtent([1, 60]).on("zoom", (e) => g.attr("transform", e.transform));
      svg.call(zoom);
      const formas = g.selectAll("path").data(geo).join("path")
        .attr("class", (d) => "pais" + (conLiga.has(d.properties.name) ? " con-datos" : ""))
        .on("click", (e, d) => { if (conLiga.has(d.properties.name)) location.hash = "#/mapa/" + encodeURIComponent(d.properties.name); });
      formas.append("title");
      M = { svg, formas, pr, trazo, zoom };
      $("#z-mas").onclick = () => svg.transition().call(zoom.scaleBy, 1.7);
      $("#z-menos").onclick = () => svg.transition().call(zoom.scaleBy, 1 / 1.7);
      $("#z-mundo").onclick = () => { location.hash = "#/mapa"; };
      const { width, height } = svg.node().getBoundingClientRect();
      pr.fitExtent([[8, 8], [width - 8, height - 30]], { type: "FeatureCollection", features: geo });
      formas.attr("d", trazo);
    }
    const total = d3.rollup(filtrados.filter((j) => j.pais), (x) => d3.sum(x, (j) => j.valor), (j) => enMapa(j.pais));
    const cuenta = d3.rollup(filtrados.filter((j) => j.pais), (x) => x.length, (j) => enMapa(j.pais));
    const color = d3.scaleSequentialLog(d3.interpolateRgb("#1f3f66", "#3ddc97")).domain([Math.max(1e5, d3.min(total.values()) || 1e5), Math.max(2e5, d3.max(total.values()) || 2e5)]);
    M.formas.style("fill", (d) => (total.get(d.properties.name) ? color(total.get(d.properties.name)) : null))
      .classed("activo", (d) => d.properties.name === ruta.arg);
    M.formas.select("title").text((d) => { const n = d.properties.name; return total.get(n) ? `${n}: ${mil(cuenta.get(n))} jugadores · ${eur(total.get(n))}` : n; });
    enfocar();
    ruta.arg ? lateralPais() : lateralMundo(total, cuenta);
  }
  function enfocar() {
    const { svg, trazo, zoom } = M, { width, height } = svg.node().getBoundingClientRect();
    const f = ruta.arg && geo.find((d) => d.properties.name === ruta.arg);
    if (!f) return svg.transition().duration(600).call(zoom.transform, d3.zoomIdentity);
    let principal = f;                                       // el polígono mayor: evita encuadrar territorios de ultramar
    if (f.geometry.type === "MultiPolygon") {
      const mayor = f.geometry.coordinates.map((c) => ({ type: "Polygon", coordinates: c })).sort((a, b) => d3.geoArea(b) - d3.geoArea(a))[0];
      principal = { type: "Feature", geometry: mayor };
    }
    const [[x0, y0], [x1, y1]] = trazo.bounds(principal);
    const k = Math.min(50, 0.75 / Math.max((x1 - x0) / width, (y1 - y0) / height));
    svg.transition().duration(700).call(zoom.transform, d3.zoomIdentity.translate(width / 2, height / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2));
  }
  function lateralMundo() {
    const porPais = d3.rollups(filtrados.filter((j) => j.pais), (x) => ({ n: x.length, v: d3.sum(x, (j) => j.valor), v3: d3.sum(x, (j) => j.v3 ?? j.valor) }), (j) => j.pais)
      .sort((a, b) => b[1].v - a[1].v);
    const tv = d3.sum(filtrados, (j) => j.valor), t3 = d3.sum(filtrados, (j) => j.v3 ?? j.valor), mx = porPais.length ? porPais[0][1].v : 1;
    $("#lateral").innerHTML = `<h1>Mercado mundial</h1><p class="nota">Valor de mercado de los jugadores que pasan los filtros, por país de su liga. Toca un país en el mapa o en la lista.</p>
      <div class="kpis"><div class="kpi"><b>${mil(filtrados.length)}</b><span>jugadores</span></div><div class="kpi"><b>${eur(tv)}</b><span>valor actual</span></div>
      <div class="kpi"><b class="${tono(t3 / tv - 1)}">${pct(t3 / tv - 1)}</b><span>mediana a 3 años</span></div></div>
      <h3>Países (${porPais.length})</h3>${porPais.map(([p, s]) => `<a class="fila" href="#/mapa/${encodeURIComponent(enMapa(p))}">
        <span class="n">${esc(es(p))}</span><span class="s">${mil(s.n)} jugadores</span>
        <span class="v">${eur(s.v)}<small class="${tono(s.v3 / s.v - 1)}">${pct(s.v3 / s.v - 1)} 3a</small></span><i class="barrita" style="width:${Math.max(2, 100 * s.v / mx)}%"></i></a>`).join("")}`;
  }
  function lateralPais() {
    const paises = paisesLiga.filter((p) => enMapa(p) === ruta.arg);
    const js = filtrados.filter((j) => paises.includes(j.pais));
    const ligas = d3.rollups(js, (x) => x, (j) => j.pais + "|" + j.liga).map(([k, x]) => ({ k, x, c: x[0].c, v: d3.sum(x, (j) => j.valor) }))
      .sort((a, b) => a.c.nivel - b.c.nivel || b.v - a.v);
    const titulo = paises.map(es).join(", ") || ruta.arg;
    $("#lateral").innerHTML = `<div class="migas"><a href="#/mapa">Mundo</a> › ${esc(titulo)}</div><h1>${esc(titulo)}</h1>
      <div class="kpis"><div class="kpi"><b>${mil(js.length)}</b><span>jugadores</span></div><div class="kpi"><b>${eur(d3.sum(js, (j) => j.valor))}</b><span>valor actual</span></div></div>
      <p><a class="chip" href="#/explorar" data-pais="${esc(paises[0] || "")}">Ver todos en el explorador →</a></p>`
      + (ligas.map((l) => {
        const cl = d3.rollups(l.x, (x) => ({ n: x.length, v: d3.sum(x, (j) => j.valor), v3: d3.sum(x, (j) => j.v3 ?? j.valor) }), (j) => j.club).sort((a, b) => b[1].v - a[1].v);
        return `<h3>${esc(l.c.liga)}${paises.length > 1 ? " · " + esc(es(l.c.pais)) : ""} · ${NIVEL[Math.min(l.c.nivel, 9) > 5 && l.c.nivel < 9 ? 5 : l.c.nivel]} · ${eq(cl.length)}</h3>`
          + (l.c.nivel === 9 ? `<p class="nota">Clubes cuya liga no viene en los datos; el país se infirió por la nacionalidad dominante de la plantilla.</p>` : "")
          + cl.slice(0, l.c.nivel === 9 ? 15 : 40).map(([id, s]) => `<a class="fila" href="#/club/${id}"><span class="n">${esc(club.get(id).nombre)}</span>
            <span class="s">${s.n} jugadores</span><span class="v">${eur(s.v)}<small class="${tono(s.v3 / s.v - 1)}">${pct(s.v3 / s.v - 1)} 3a</small></span></a>`).join("");
      }).join("") || `<p class="nota">Ningún jugador de este país pasa los filtros.</p>`);
    if (innerWidth <= 900) $("#lateral").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ================================================================ vista: radar
  const TABLEROS = [
    { id: "apuestas", t: "Apuestas del modelo", d: `Hasta 23 años, €1–25M, en liga con datos completos: los de mayor alza esperada. En las pruebas retrospectivas, las 50 apuestas de cada año multiplicaron su valor por ${mediaDe(RT.picks, "sel_mult").toFixed(1)} en tres años (mediana), contra ${mediaDe(RT.picks, "pob_mult").toFixed(1)} del grupo.`,
      f: (j) => j.edad <= 23 && j.valor >= 1e6 && j.valor <= 25e6 && j.cubierta && j.r3 != null, k: (j) => -j.r3, r: (j) => `${eur(j.valor)} → ${eur(j.v3)}<small class="sube">${pct(j.r3)} · techo ${eur(j.techo)}</small>`, o: "r3", fl: { emax: 23, vmin: 1, vmax: 25, nivel: 1 } },
    { id: "alertas", t: "Alertas de devaluación", d: `27 años o más, desde €5M, en liga con datos completos: los de mayor caída esperada. En las pruebas, ${Math.round(100 * mediaDe(RT.picks, "al_cae"))}% de las 50 alertas de cada año perdió al menos 40% en tres años, contra ${Math.round(100 * mediaDe(RT.picks, "viej_cae"))}% del grupo.`,
      f: (j) => j.edad >= 27 && j.valor >= 5e6 && j.cubierta && j.r3 != null, k: (j) => j.r3, r: (j) => `${eur(j.valor)} → ${eur(j.v3)}<small class="baja">${pct(j.r3)} · ${eur(j.d3)}</small>`, o: "r3", asc: true, fl: { emin: 27, vmin: 5, nivel: 1 } },
    { id: "prima", t: "Se pagan por encima de su valor", d: "Desde €2M en liga con datos completos: mayor diferencia entre el precio de traspaso estimado y el valor de Transfermarkt.",
      f: (j) => j.valor >= 2e6 && j.cubierta, k: (j) => -j.prima, r: (j) => `${eur(j.valor)} TM → ${eur(j.precio)}<small class="sube">${pct(j.prima)} · hasta ${eur(j.pHi95)}</small>`, o: "precio", fl: { vmin: 2, nivel: 1 } },
    { id: "alza", t: "Mayor revalorización esperada", d: "Ganancia mediana esperada a 3 años.", f: (j) => j.d3 > 0, k: (j) => -j.d3, r: (j) => `${eur(j.valor)} → ${eur(j.v3)}<small class="sube">${eur(j.d3)} · ${pct(j.r3)}</small>`, o: "d3" },
    { id: "promesas", t: "Promesas sub-21 con mayor techo", d: "Valor máximo de carrera esperado (mediana) y escenario optimista.", f: (j) => j.edad <= 21, k: (j) => -j.pico, r: (j) => `${eur(j.valor)} → ${eur(j.pico)}<small>techo ${eur(j.techo)}</small>`, o: "pico", fl: { emax: 21 } },
    { id: "gangas", t: "Fuera de primera división, al alza", d: "Divisiones inferiores con mayor crecimiento porcentual esperado (valor ≥ €300k).", f: (j) => j.nivel >= 2 && j.nivel <= 8 && j.valor >= 3e5 && j.r3 > 0, k: (j) => -j.r3, r: (j) => `${eur(j.valor)} → ${eur(j.v3)}<small class="sube">${pct(j.r3)} · ${esc(j.liga)}</small>`, o: "r3" },
    { id: "baja", t: "Mayor devaluación esperada", d: "Pérdida mediana a 3 años: activos que conviene vender antes.", f: (j) => j.d3 < 0, k: (j) => j.d3, r: (j) => `${eur(j.valor)} → ${eur(j.v3)}<small class="baja">${eur(j.d3)} · ${pct(j.r3)}</small>`, o: "d3", asc: true },
    { id: "contratos", t: "Contratos que vencen en 12 meses", d: "Los más valiosos que pueden salir libres o negociar ya.", f: (j) => j.meses != null && j.meses <= 12 && j.meses >= 0 && j.nivel > 0, k: (j) => -j.valor, r: (j) => `${eur(j.valor)}<small>vence ${fechaYM(+j.contrato.replace("-", ""))}</small>`, o: "valor", fl: { contrato: 12 } },
    { id: "libres", t: "Agentes libres más valiosos", d: "Sin club en la última actualización de la fuente.", f: (j) => j.nivel === 0, k: (j) => -j.valor, r: (j) => `${eur(j.valor)}<small>máx. histórico ${eur(j.maxHist)}</small>`, o: "valor", fl: { nivel: 0 } },
    { id: "veteranos", t: "Veteranos que más valor conservan", d: "33 años o más: valor mediano esperado dentro de 3 años.", f: (j) => j.edad >= 33 && j.v3 != null, k: (j) => -j.v3, r: (j) => `${eur(j.valor)} → ${eur(j.v3)}<small class="${tono(j.r3)}">${pct(j.r3)}</small>`, o: "v3", fl: { emin: 33 } },
    { id: "rebote", t: "Lejos de su máximo y repuntando", d: "Valen menos de la mitad de su máximo histórico, pero el modelo espera subida.", f: (j) => j.valor < j.maxHist * 0.5 && j.r3 > 0.1 && j.valor >= 5e5, k: (j) => -j.d3, r: (j) => `${eur(j.valor)} → ${eur(j.v3)}<small>máx. ${eur(j.maxHist)}</small>`, o: "d3" },
  ];
  function vistaRadar() {
    $("#vista").innerHTML = `<div class="pagina"><div class="cabecera"><div><h1>Radar</h1><p class="tenue">Once lecturas del mercado sobre los ${mil(filtrados.length)} jugadores que pasan los filtros. Cámbialos arriba para acotar por liga, posición o edad.</p></div></div>
      <div class="rejilla">${TABLEROS.map((t) => {
        const top = filtrados.filter(t.f).sort((a, b) => t.k(a) - t.k(b)).slice(0, 8);
        return `<section class="tarjeta tablero"><h2>${t.t}<a href="#/explorar" data-tablero="${t.id}">Ver todos →</a></h2><p class="nota">${t.d}</p>
          ${top.map((j) => filaJ(j, t.r)).join("") || `<p class="nota">Sin resultados con estos filtros.</p>`}</section>`;
      }).join("")}</div></div>`;
  }

  // ================================================================ vista: explorador
  function vistaExplorar() {
    $("#vista").innerHTML = `<div class="pagina"><div class="cabecera"><div><h1>Explorador</h1><p class="tenue">Ordena por cualquier columna. Las proyecciones son medianas en euros corrientes.</p></div></div>
      ${tabla("explorar", filtrados, ["nombre", "pos", "edad", "liga", "valor", "precio", "v1", "v3", "r3", "d3", "v5", "pico", "techo", "perfil", "contrato", "min"])}</div>`;
  }

  // ================================================================ vista: club
  function vistaClub() {
    const c = club.get(+ruta.arg);
    if (!c) return ($("#vista").innerHTML = `<div class="pagina"><p>Club no encontrado.</p></div>`);
    const js = jugadores.filter((j) => j.club === c.id), v = d3.sum(js, (j) => j.valor), v3 = d3.sum(js, (j) => j.v3 ?? j.valor);
    const vence = js.filter((j) => j.meses != null && j.meses <= 12 && j.meses >= 0);
    const edadPond = d3.sum(js, (j) => j.edad * j.valor) / (v || 1);
    $("#vista").innerHTML = `<div class="pagina">
      <div class="migas"><a href="#/mapa">Mundo</a>${c.pais ? ` › <a href="#/mapa/${encodeURIComponent(enMapa(c.pais))}">${esc(es(c.pais))}</a>` : ""} › ${esc(c.nombre)}</div>
      <div class="cabecera"><div><h1>${esc(c.nombre)}</h1><p class="tenue">${esc(c.liga)} · ${NIVEL[c.nivel > 5 && c.nivel < 9 ? 5 : c.nivel]}${c.estadio ? " · " + esc(c.estadio) : ""}${c.inf ? " · país inferido" : ""}</p></div></div>
      <div class="kpis">
        <div class="kpi"><b>${eur(v)}</b><span>valor de la plantilla</span></div>
        <div class="kpi"><b class="${tono(v3 / v - 1)}">${eur(v3)}</b><span>mediana a 3 años (${pct(v3 / v - 1)}), sin altas ni bajas</span></div>
        <div class="kpi"><b>${js.length}</b><span>jugadores · edad media ${d3.mean(js, (j) => j.edad)?.toFixed(1) ?? "—"}</span></div>
        <div class="kpi"><b>${edadPond.toFixed(1)}</b><span>edad ponderada por valor</span></div>
        <div class="kpi"><b>${eur(d3.sum(vence, (j) => j.valor))}</b><span>valor con contrato que vence en 12 meses (${vence.length})</span></div>
        <div class="kpi"><b class="baja">${eur(d3.sum(js, (j) => Math.min(0, j.d3 ?? 0)))}</b><span>devaluación esperada a 3 años de quienes bajan</span></div>
        <div class="kpi"><b>${eur(d3.sum(js, (j) => j.precio))}</b><span>precio de venta estimado de la plantilla (${pct(d3.sum(js, (j) => j.precio) / v - 1)} vs TM)</span></div>
      </div>
      <div class="tarjeta"><h2>Edad y valor de la plantilla</h2><p class="nota">Cada punto es un jugador; el color es la señal a 3 años. Arriba a la izquierda están los activos por revalorizar; abajo a la derecha, los que se deprecian.</p><svg class="grafica" id="dispersion"></svg></div>
      <h3>Plantilla</h3>${tabla("club" + c.id, js, ["nombre", "pos", "edad", "valor", "v1", "v3", "r3", "d3", "pico", "perfil", "contrato", "min"], "valor", 60)}</div>`;
    const el = d3.select("#dispersion"), W = el.node().clientWidth, H = 280, m = { t: 10, r: 14, b: 26, l: 50 };
    el.attr("viewBox", `0 0 ${W} ${H}`).attr("height", H);
    if (!js.length) return;
    const x = d3.scaleLinear([Math.min(16, d3.min(js, (j) => j.edad)) - 1, Math.max(36, d3.max(js, (j) => j.edad)) + 1], [m.l, W - m.r]);
    const y = d3.scaleLog([Math.max(1e4, d3.min(js, (j) => j.valor) * 0.7), d3.max(js, (j) => j.valor) * 1.4], [H - m.b, m.t]);
    el.append("g").attr("class", "eje").attr("transform", `translate(0,${H - m.b})`).call(d3.axisBottom(x).ticks(10).tickFormat((d) => d + " a"));
    el.append("g").attr("class", "eje").attr("transform", `translate(${m.l},0)`)
      .call(d3.axisLeft(y).tickValues([1e4, 3e4, 1e5, 3e5, 1e6, 3e6, 1e7, 3e7, 1e8, 3e8].filter((t) => t >= y.domain()[0] && t <= y.domain()[1])).tickFormat(eur));
    const col = ["#3ddc97", "#8b9bbb", "#f0707d"];
    el.selectAll("circle").data(js).join("circle").attr("cx", (j) => x(j.edad) + ((j.id % 7) - 3) * 1.6).attr("cy", (j) => y(j.valor)).attr("r", 5.5)
      .attr("fill", (j) => col[j.senal]).attr("fill-opacity", .8).attr("stroke", "#0f1626").style("cursor", "pointer")
      .on("click", (e, j) => abrirJ(j.id)).append("title").text((j) => `${j.nombre} · ${j.edad} años · ${eur(j.valor)} → ${eur(j.v3)} a 3 años`);
  }

  // ================================================================ vista: mi lista
  let comparar = new Set();
  const PALETA = ["#3ddc97", "#6aa9f7", "#f4bf4f", "#b99cf5", "#f0707d", "#5fd3e0"];
  function vistaLista() {
    const js = [...lista].map((id) => porId.get(id)).filter(Boolean);
    comparar = new Set([...comparar].filter((id) => lista.has(id)));
    if (!comparar.size) js.slice(0, 4).forEach((j) => comparar.add(j.id));
    $("#vista").innerHTML = `<div class="pagina"><div class="cabecera"><div><h1>Mi lista</h1><p class="tenue">Jugadores que marcaste con ★. Se guarda sólo en este navegador.</p></div></div>
      ${js.length ? `<div class="tarjeta"><h2>Comparar trayectorias</h2><p class="nota">Mediana proyectada a 8 años. Elige hasta 6.</p>
        <div class="chips">${js.map((j) => `<span class="chip ${comparar.has(j.id) ? "on" : ""}" data-comparar="${j.id}">${esc(j.nombre)}</span>`).join("")}</div>
        <svg class="grafica" id="comparacion"></svg></div>
        <h3>Seguimiento</h3>${tabla("lista", js, ["nombre", "pos", "edad", "liga", "valor", "precio", "v1", "v3", "r3", "v5", "pico", "techo", "perfil", "contrato"], "valor")}`
        : `<div class="tarjeta"><p>Tu lista está vacía. Marca jugadores con ★ desde el explorador, el radar o su ficha.</p></div>`}</div>`;
    if (!js.length) return;
    const sel = js.filter((j) => comparar.has(j.id)).slice(0, 6);
    const el = d3.select("#comparacion"), W = el.node().clientWidth, H = 280, m = { t: 10, r: 110, b: 26, l: 50 };
    el.attr("viewBox", `0 0 ${W} ${H}`).attr("height", H);
    const series = sel.map((j) => ({ j, pts: [[0, j.valor]].concat(d3.range(1, 9).map((h) => [h, med(j, h)]).filter((p) => p[1] != null)) }));
    const x = d3.scaleLinear([0, 8], [m.l, W - m.r]), y = d3.scaleLinear([0, (d3.max(series, (s) => d3.max(s.pts, (p) => p[1])) || 1) * 1.08], [H - m.b, m.t]);
    el.append("g").attr("class", "eje").attr("transform", `translate(0,${H - m.b})`).call(d3.axisBottom(x).ticks(8).tickFormat((d) => (d ? "+" + d + " a" : "hoy")));
    el.append("g").attr("class", "eje").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5).tickFormat(eur));
    series.forEach((s, i) => {
      el.append("path").attr("fill", "none").attr("stroke", PALETA[i]).attr("stroke-width", 2).attr("d", d3.line().x((p) => x(p[0])).y((p) => y(p[1]))(s.pts));
      const u = s.pts[s.pts.length - 1];
      el.append("text").attr("x", x(u[0]) + 6).attr("y", y(u[1]) + 3).attr("fill", PALETA[i]).attr("font-size", 11).text(s.j.nombre.split(" ").slice(-1)[0]);
    });
  }

  // ================================================================ vista: metodología
  function vistaMetodo() {
    const G = { liga: "En ligas con datos completos", sub23: "· menores de 23", "23a28": "· 23 a 28 años", "29mas": "· 29 años o más", "10M": "Valor ≥ €10M", todos: "Todos (incluye divisiones sin datos de club)" };
    const p100 = (x) => Math.round(x * 100) + "%";
    const viejos = jugadores.filter((j) => j.fecha < corteYM - 100).length, sinPais = jugadores.filter((j) => !j.pais).length, sinCob = jugadores.filter((j) => !j.cubierta).length;
    const ag = (h, g) => RT.agregada.find((r) => r.h === h && r.grupo === g);
    const P = RT.picks, casos = RT.casos;
    const veredicto = (c) => (c.real == null ? "sin valor" : c.real > c.p98 ? "por encima de todo lo previsto" : c.real > c.p90 ? "por encima de la banda" : c.real < c.p02 ? "por debajo de todo lo previsto" : c.real < c.p10 ? "por debajo de la banda" : "dentro de la banda");
    $("#vista").innerHTML = `<div class="pagina" style="max-width:1040px"><h1>Metodología, precisión y límites</h1>
      <p class="tenue">Qué hace el modelo, cuánto acierta medido contra el pasado y dónde no se le debe creer.</p>
      <div class="kpis"><div class="kpi"><b>${mil(meta.jugadores)}</b><span>jugadores vigentes</span></div><div class="kpi"><b>${mil(meta.valuaciones)}</b><span>valuaciones históricas de ${mil(meta.jugadores_historia)} jugadores</span></div>
        <div class="kpi"><b>${mil(meta.filas_modelo)}</b><span>observaciones jugador-año para entrenar</span></div><div class="kpi"><b>${meta.rasgos}</b><span>variables por jugador</span></div></div>

      <h3>Cómo leer los números: confianza no es lo mismo que precisión</h3>
      <div class="tarjeta"><p><b>Confianza</b> es cuántas veces el valor real cae dentro del rango que da el modelo. Aquí es 95%, y está comprobado contra diez años de historia: no es una promesa, es una medición.</p>
        <p><b>Precisión</b> es qué tan angosto es ese rango. «Error típico de ${p100(ag(3, "liga").modelo)} a tres años» no significa acertar ${Math.round(10 - 10 * ag(3, "liga").modelo)} de cada 10: significa que la cifra central se desvía típicamente esa proporción del valor real (una proyección de €10M suele terminar entre €${(10 / (1 + ag(3, "liga").modelo)).toFixed(0)}M y €${(10 * (1 + ag(3, "liga").modelo)).toFixed(1)}M). El rango de 95% es mucho más ancho, porque incluye también los casos raros.</p>
        <p>Subir la confianza es cuestión de ensanchar el rango. Estrecharlo sin perder confianza sólo se logra con mejores datos.</p></div>

      <h3>La respuesta corta</h3>
      <div class="tarjeta"><p><b>Nadie puede proyectar el valor de un futbolista «al centavo», y este modelo tampoco.</b> A tres años, la proyección central se desvía típicamente ${p100(ag(3, "liga").modelo)} del valor real (contra ${p100(ag(3, "liga").ingenuo)} de suponer que el valor no cambia). En 2018 Haaland valía €300 mil y ningún dato disponible ese día apuntaba a €200 millones.</p>
        <p><b>Lo que sí hace bien es ordenar.</b> En cada año de prueba, sus 50 apuestas sub-23 multiplicaron su valor por ${mediaDe(P, "sel_mult").toFixed(1)} en tres años (mediana), contra ${mediaDe(P, "pob_mult").toFixed(1)} del grupo del que salieron; y ${p100(mediaDe(P, "al_cae"))} de sus 50 alertas de devaluación perdió al menos 40% de valor. Sirve para decidir dónde mirar y qué vender, no para fijar un precio.</p></div>

      <h3>Cómo funciona</h3>
      <div class="tarjeta"><p><b>1. Modelo de precisión.</b> Árboles de decisión potenciados (gradient boosting) entrenados por cuantiles: uno para el escenario pesimista, otro para la mediana y otro para el optimista, a 1, 3, 5 y 8 años (los intermedios se interpolan). Cada jugador-año aporta ${meta.rasgos} variables: edad exacta, posición, valor y su trayectoria (6 meses, 1, 2 y 3 años, distancia a su máximo), club y liga en esa fecha (valor de la plantilla, su lugar dentro de ella, nivel de la liga), minutos, goles y asistencias de los 12 meses previos, minutos europeos y de selección, acumulados de carrera, fichajes recientes, días de lesión, partidos y goles en todas las competiciones (también divisiones inferiores), historial de traspasos y cesiones, media y potencial de EA FC con años de contrato y cláusula, y puesto en liga y Elo del club. Proyecta en euros corrientes: aprende el cambio típico de cada tipo de jugador, inflación incluida, y supone que el mercado seguirá comportándose como su promedio histórico.</p>
        <p><b>2. Curva de largo plazo.</b> Más allá de 8 años no hay datos suficientes para un modelo individual; la proyección se prolonga con la forma típica por edad, posición y nivel de valor (factores de desarrollo edad a edad, como un triángulo actuarial).</p>
        <p><b>3. Rangos con confianza comprobada.</b> Cada proyección trae dos rangos, escalados con el error observado en las pruebas retrospectivas (calibración conforme: no supone ninguna distribución). Medido dejando fuera cada año evaluado, el rango de 95% contuvo el valor real ${Object.entries(RT.cobertura95).map(([h, c]) => `${p100(c)} de las veces a ${h} año${h > 1 ? "s" : ""}`).join(", ")}; el de 80%, ${Object.entries(RT.cobertura).map(([h, c]) => p100(c)).join(", ")}.</p>
        <p><b>4. Precedentes.</b> En cada ficha, los cinco jugadores históricos más parecidos y qué fue de ellos. No alimentan el número: sirven para juzgarlo.</p></div>

      <h3>Precisión: prueba retrospectiva de origen móvil</h3>
      <p class="nota">Para cada año de ${RT.origenes[0]} a ${RT.origenes[1]} el modelo se reentrenó usando sólo lo que se sabía ese 1 de julio y se comparó con el valor real 1, 3 y 5 años después. «Error típico» = mediana de la desviación de la proyección central. «Ingenuo» = suponer que el valor no cambia. «Orden» = correlación de rangos entre el cambio previsto y el real (0 = azar, 1 = perfecto).</p>
      <div class="tabla-caja"><table class="plana"><thead><tr><th class="izq">Horizonte</th><th class="izq">Grupo</th><th>Casos</th><th>Error típico</th><th>Ingenuo</th><th>Orden</th></tr></thead>
      <tbody>${[1, 3, 5].flatMap((h) => Object.keys(G).map((g) => ag(h, g)).filter(Boolean).map((r) => `<tr><td class="izq">${r.h} año${r.h > 1 ? "s" : ""}</td><td class="izq">${G[r.grupo]}</td><td>${mil(r.n)}</td>
        <td><b>${p100(r.modelo)}</b></td><td>${p100(r.ingenuo)}</td><td>${r.spearman.toFixed(2)}</td></tr>`)).join("")}</tbody></table></div>


      <h3>Precio pagado frente a valor de Transfermarkt</h3>
      <p class="nota">El valor de Transfermarkt es una estimación de su comunidad; lo que un club paga es otra cosa. Con ${mil(RT.precio.n)} traspasos que tienen cuota divulgada y valor en la fecha se modela cuánto se paga por un jugador así. Cociente observado cuota ÷ valor en los últimos años:</p>
      <div class="tabla-caja"><table class="plana"><thead><tr><th class="izq">Edad al traspaso</th><th>Traspasos</th><th>Se paga (mediana)</th><th>Cuartil bajo</th><th>Cuartil alto</th></tr></thead>
      <tbody>${RT.precio.por_edad.map((r) => `<tr><td class="izq">${r.grupo}</td><td>${mil(r.n)}</td><td><b>×${r.multiplo.toFixed(2)}</b></td><td>×${r.bajo.toFixed(2)}</td><td>×${r.alto.toFixed(2)}</td></tr>`).join("")}</tbody></table></div>
      <p class="nota">Prueba retrospectiva: para cada temporada el modelo se entrenó sólo con traspasos anteriores y se comparó con las cuotas reales de esa temporada. «Pagar el valor de TM» es la referencia.</p>
      <div class="tabla-caja"><table class="plana"><thead><tr><th class="izq">Temporada</th><th>Traspasos</th><th>Error típico del modelo</th><th>Suponer cuota = valor TM</th><th>Menores de 22: modelo</th><th>Menores de 22: valor TM</th><th>Orden</th></tr></thead>
      <tbody>${RT.precio.por_temporada.map((r) => `<tr><td class="izq">${r.temporada}/${String(r.temporada + 1).slice(2)}</td><td>${mil(r.n)}</td><td><b>${p100(r.modelo)}</b></td><td>${p100(r.tm)}</td><td><b>${p100(r.modelo_sub22)}</b></td><td>${p100(r.tm_sub22)}</td><td>${r.orden.toFixed(2)}</td></tr>`).join("")}</tbody></table></div>
      <p class="nota">El rango de precio de 95% contuvo ${p100(RT.precio.cobertura95)} de las cuotas reales fuera de muestra (el de 80%, ${p100(RT.precio.cobertura)}). <b>Límite importante:</b> sólo se observan traspasos con cuota divulgada; los libres, las cesiones y los jugadores que nadie compró no están. El precio estimado se lee como «si se vende con cuota, esto se paga por alguien así», no como el precio al que cualquiera lo conseguiría. No ve la duración del contrato ni cláusulas.</p>

      <h3>¿Sirve para elegir?</h3>
      <p class="nota">Cada año, entre los sub-23 de €1–25M en ligas con datos completos, se tomaron las 50 mayores alzas previstas; y entre los de 27 años o más desde €5M, las 50 mayores caídas previstas. Resultado tres años después (sólo quienes seguían valuados).</p>
      <div class="tabla-caja"><table class="plana"><thead><tr><th class="izq">Año de la apuesta</th><th>Múltiplo mediano: 50 apuestas</th><th>Grupo completo</th><th>Duplicaron valor: apuestas</th><th>Grupo</th><th>Valor de la cartera: apuestas</th><th>Grupo</th><th>Alertas que cayeron ≥40%</th><th>Grupo</th></tr></thead>
      <tbody>${P.map((r) => `<tr><td class="izq">${r.origen}</td><td><b>×${r.sel_mult.toFixed(2)}</b></td><td>×${r.pob_mult.toFixed(2)}</td><td><b>${p100(r.sel_doble)}</b></td><td>${p100(r.pob_doble)}</td>
        <td><b>×${r.sel_cartera.toFixed(2)}</b></td><td>×${r.pob_cartera.toFixed(2)}</td><td><b>${p100(r.al_cae)}</b></td><td>${p100(r.viej_cae)}</td></tr>`).join("")}</tbody></table></div>
      <p class="nota">Son valuaciones de Transfermarkt, no precios pagados: comprar a ese valor no siempre es posible y los traspasos reales incluyen primas. El múltiplo de cartera es una medida de selección, no un rendimiento financiero.</p>

      <h3>Lo que habría dicho de casos conocidos</h3>
      <div class="tabla-caja"><table class="plana"><thead><tr><th class="izq">Jugador</th><th class="izq">Proyección hecha en</th><th>Valía</th><th>Pesimista</th><th>Mediana</th><th>Optimista</th><th>Extremo (1 de 50)</th><th>Valor real</th><th class="izq">Resultado</th></tr></thead>
      <tbody>${casos.map((c) => `<tr><td class="izq">${esc(c.nombre)} <span class="tenue">(${c.edad})</span></td><td class="izq">${c.origen} → ${c.origen + c.h}</td><td>${eur(c.valor)}</td><td>${eur(c.p10)}</td><td>${eur(c.p50)}</td><td>${eur(c.p90)}</td><td>${eur(c.p98)}</td>
        <td><b>${eur(c.real)}</b></td><td class="izq ${c.real > c.p90 ? "sube" : c.real < c.p10 ? "baja" : ""}">${veredicto(c)}</td></tr>`).join("")}</tbody></table></div>
      <p class="nota">Los casos se eligieron antes de ver el resultado del modelo e incluyen fracasos sonados a propósito. Las grandes estrellas quedan casi siempre fuera de la banda: son, por definición, lo que nadie veía venir.</p>

      <h3>Detalle por año de origen (ligas con datos completos)</h3>
      <div class="tabla-caja"><table class="plana"><thead><tr><th class="izq">Origen</th>${[1, 3, 5].map((h) => `<th>Error a ${h}a</th><th>Ingenuo</th><th>Orden</th>`).join("")}</tr></thead>
      <tbody>${[...new Set(RT.por_origen.map((r) => r.origen))].map((o) => `<tr><td class="izq">${o}</td>${[1, 3, 5].map((h) => { const r = RT.por_origen.find((x) => x.origen === o && x.h === h); return r ? `<td><b>${p100(r.modelo)}</b></td><td>${p100(r.ingenuo)}</td><td>${r.spearman.toFixed(2)}</td>` : "<td>—</td><td>—</td><td>—</td>"; }).join("")}</tr>`).join("")}</tbody></table></div>

      <h3>El mercado como fuente de error</h3>
      <div class="tarjeta"><p class="nota">Valor medio de los 500 jugadores más caros de cada año (${meta.indice_mercado.anios[0]} = 1). La élite subió ${(meta.inflacion_10a * 100).toFixed(1)}% anual en 10 años, casi todo en el salto de 2017–2019; desde 2019, ${(INFL_RECIENTE * 100).toFixed(1)}% anual. Ningún modelo anticipa esos cambios de régimen, y son una parte del error que no depende del jugador. Se probó descontar este índice (y uno más amplio) antes de entrenar: la precisión no mejoró, así que el modelo trabaja directamente en euros corrientes.</p><svg class="grafica" id="indice"></svg></div>

      <h3>Límites</h3>
      <div class="tarjeta"><ul>
        <li><b>El techo de precisión lo pone el fútbol, no la falta de datos.</b> Además de modelos más grandes, se rastrearon más de 60 conjuntos de datos abiertos y se integraron los más fuertes: partidos y goles en 1,643 competiciones, historial completo de traspasos y cesiones, media y potencial de EA FC con contrato y cláusula, tabla de liga y Elo del club. El error típico casi no cambió; mejoró el orden entre jugadores y la calidad de las apuestas. El valor de Transfermarkt ya incorpora casi todo lo que es público.</li>
        <li><b>Se proyecta la valuación de Transfermarkt</b>, una estimación de su comunidad, no precios de traspaso.</li>
        <li><b>${mil(sinCob)} jugadores están fuera de las ligas con datos completos.</b> Para ellos el modelo no ve club, minutos ni goles y sus proyecciones son menos finas; la ficha lo avisa.</li>
        <li><b>${mil(viejos)} valores tienen más de un año</b> (una fuente dejó de actualizar valuaciones en septiembre de 2025). Cada ficha muestra la fecha de su valor.</li>
        <li><b>${mil(sinPais)} jugadores no tienen país de liga</b> y no aparecen en el mapa; sí en el explorador. En otros clubes el país es inferido por la nacionalidad dominante de la plantilla.</li>
        <li><b>Sesgo de supervivencia.</b> Cada año ${Math.round(meta.salida_anual * 100)}% de los jugadores deja de estar valuado. Las bandas son para quien sigue; cada horizonte muestra la probabilidad de seguir valuado.</li>
        <li><b>Sesgo de selección corregido.</b> Una de las fuentes sólo incluye a un jugador si alguna vez llegó a una liga cubierta; sus años previos se excluyeron de entrenamiento y evaluación, porque sólo existen gracias a que después triunfó.</li>
        <li><b>No entran al modelo</b> duración del contrato (sólo se conoce la actual), salario ni exposición mediática.</li>
        <li><b>Por encima de €100M, por encima de 38 años y más allá de 8 años</b> hay pocos casos: ahí el modelo extrapola.</li>
        <li>Los perfiles (Estrella ≥ €60M, Élite ≥ €25M, Cumplidor ≥ €8M, Regular ≥ €2M, De rol) son cortes convencionales sobre el valor máximo esperado en los próximos 8 años o el ya alcanzado.</li></ul></div>
      <p class="nota">Fuentes: dcaribou/transfermarkt-datasets (corte ${meta.corte}); salimt/football-datasets (valuaciones, rendimiento y traspasos a septiembre de 2025, lesiones a septiembre de 2026); Football Transfers Dataset 2005–2024 (Zenodo, CC BY 4.0); ediciones FIFA 15 a FC 26 (datos de sofifa en espejos abiertos); ClubElo vía espejo abierto.</p></div>`;
    const el = d3.select("#indice"), W = el.node().clientWidth, H = 200, m = { t: 8, r: 10, b: 22, l: 36 }, I = meta.indice_mercado;
    el.attr("viewBox", `0 0 ${W} ${H}`).attr("height", H);
    const x = d3.scaleLinear(d3.extent(I.anios), [m.l, W - m.r]), y = d3.scaleLinear([0, d3.max(I.valor) * 1.05], [H - m.b, m.t]);
    el.append("g").attr("class", "eje").attr("transform", `translate(0,${H - m.b})`).call(d3.axisBottom(x).ticks(8).tickFormat(d3.format("d")));
    el.append("g").attr("class", "eje").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5).tickFormat((d) => "×" + d));
    el.append("path").attr("class", "historia").attr("d", d3.line().x((d, i) => x(I.anios[i])).y((d) => y(d))(I.valor));
  }

  // ================================================================ ficha del jugador
  const trozos = new Map();
  const detalle = (id) => {
    const k = id % meta.trozos;
    if (!trozos.has(k)) trozos.set(k, fetch(`datos/det/${k}.json`).then((r) => r.json()));
    return trozos.get(k).then((t) => t[id] || { h: [[], []] });
  };
  async function pintarFicha() {
    const el = $("#ficha"), j = ruta.j && porId.get(ruta.j);
    el.hidden = $("#velo").hidden = !j;
    document.body.style.overflow = j ? "hidden" : "";
    if (!j) return;
    const d = await detalle(j.id);
    if (ruta.j !== j.id) return;
    const c = j.c, Q = d.q || [], Sv = d.s || [];
    const proy = (h, k = 2) => (Q[h - 1] ? j.valor * Q[h - 1][k] : null);     // k: 0-4 = 95% bajo, 80% bajo, mediana, 80% alto, 95% alto
    const viejo = j.fecha < corteYM - 100;
    const horizontes = [1, 2, 3, 5, 8, 10, 15].filter((h) => h <= Q.length);
    const fila = (h) => `<tr><td class="izq">${h} año${h > 1 ? "s" : ""} · ${j.edad + h} de edad</td><td><b>${eur(proy(h))}</b></td>
      <td class="${tono(proy(h) / j.valor - 1)}">${pct(proy(h) / j.valor - 1)}</td><td>${eur(proy(h, 0))} – ${eur(proy(h, 4))}</td><td>${eur(proy(h, 1))} – ${eur(proy(h, 3))}</td>
      <td>${Sv[h - 1] == null ? "—" : Math.round(Sv[h - 1] * 100) + "%"}</td></tr>`;
    // contribución de cada grupo de factores a la mediana a 3 años (descomposición exacta del modelo)
    const hf = 3, F_ = d.f || [];
    const contrib = j.H >= 3 && F_.length ? [["Punto de partida: cambio típico de un jugador", F_[0]]].concat(meta.grupos.map((g, i) => [g, F_[i + 1]])) : [];
    const mxc = Math.max(0.05, ...contrib.map((x) => Math.abs(x[1])));
    const pr = d.p;
    el.innerHTML = `<div class="ficha-top"><div>
        <div class="migas">${c.pais ? `<a href="#/mapa/${encodeURIComponent(enMapa(c.pais))}">${esc(es(c.pais))}</a> › ` : ""}<a href="#/club/${c.id}">${esc(c.nombre)}</a></div>
        <h1>${esc(j.nombre)}</h1>
        <p class="acciones"><span class="etq e${j.etq}">${ETQ[j.etq][0]}</span><span class="etq ${SENAL[j.senal][1]}">${SENAL[j.senal][0]}</span>
          <span class="tenue">${j.subpos >= 0 ? esc(SUBPOS[meta.subposiciones[j.subpos]] || POS[j.pos]) : POS[j.pos]} · ${j.edad} años${j.nac >= 0 ? " · " + esc(es(meta.paises[j.nac])) : ""}${j.altura ? " · " + j.altura + " cm" : ""}${j.pie >= 0 ? " · " + PIE[j.pie].toLowerCase() : ""}</span></p>
      </div><div class="acciones">${estrella(j)}<button class="cerrar" data-cerrar aria-label="Cerrar">×</button></div></div>
      <div class="kpis">
        <div class="kpi"><b>${eur(j.valor)}</b><span>valor actual · ${fechaYM(j.fecha)}</span></div>
        <div class="kpi"><b class="${tono(j.r3)}">${eur(j.v3)}</b><span>mediana a ${j.h3} año${j.h3 > 1 ? "s" : ""} (${pct(j.r3)})</span></div>
        <div class="kpi"><b>${eur(j.pico)}</b><span>valor máximo esperado${j.edadPico ? " · hacia los " + j.edadPico : " · ya alcanzado"}</span></div>
        <div class="kpi"><b>${eur(j.techo)}</b><span>techo optimista (1 de cada 10)</span></div>
      </div>
      <div class="precio"><div><span class="rot">Precio de traspaso estimado hoy</span><b>${eur(j.precio)}</b>
          <span class="${tono(j.prima)}">${pct(j.prima)} respecto a su valor de Transfermarkt</span></div>
        <div class="rango"><span>con 95% de confianza, entre <b>${eur(j.pLo95)}</b> y <b>${eur(j.pHi95)}</b></span>
          <span class="nota">Con 80%: ${eur(j.pLo)} – ${eur(j.pHi)}. Es lo que se paga en traspasos con cuota de jugadores así, no lo que Transfermarkt estima.</span></div>
      </div>
      ${viejo ? `<div class="aviso">El último valor disponible es de ${fechaYM(j.fecha)}. La proyección parte de ahí y puede estar desfasada.</div>` : ""}
      ${j.valor >= 1e8 ? `<div class="aviso">Por encima de €100M casi no hay precedentes: el modelo extrapola.</div>` : ""}
      ${j.edad >= 38 ? `<div class="aviso">A esta edad hay muy pocos casos históricos; se muestra la devaluación típica de quienes siguieron activos.</div>` : ""}
      <h3>Historia y proyección</h3>
      <svg class="grafica" id="g-jugador"></svg>
      ${horizontes.length ? `<div class="tabla-caja"><table class="plana"><thead><tr><th class="izq">Horizonte</th><th>Mediana</th><th>Cambio</th><th>Rango con 95% de confianza</th><th>Rango con 80%</th><th>Sigue valuado</th></tr></thead><tbody>${horizontes.map(fila).join("")}</tbody></table></div>
        <p class="nota">El rango de 95% contiene el valor real 95 de cada 100 veces en las pruebas contra el pasado; el de 80%, 8 de cada 10. En la gráfica, la franja clara es el 95% y la oscura el 80%. «Sigue valuado» = probabilidad de seguir con valor publicado; los importes son para ese caso.</p>` : `<p class="nota">Sin proyección disponible.</p>`}
      ${!j.cubierta ? `<div class="aviso">Juega fuera de las ligas con datos completos: el modelo no ve su club, sus minutos ni sus goles, sólo su edad, posición, lesiones y la trayectoria de su valor. La proyección es menos fina.</div>` : ""}
      ${contrib.length ? `<h3>Por qué esta proyección (a ${hf} año${hf > 1 ? "s" : ""})</h3>${contrib.map(([t, x]) => `<div class="factor"><span>${t}</span>
        <span class="pista"><i style="${x >= 0 ? "left:50%" : "right:50%"};width:${Math.min(50, 50 * Math.abs(x) / mxc)}%;background:${x >= 0 ? "var(--acento)" : "var(--malo)"}"></i></span><b class="${tono(Math.exp(x) - 1)}">${pct(Math.exp(x) - 1)}</b></div>`).join("")}
        <p class="nota">Los efectos se multiplican y juntos dan la mediana a 3 años. Es la descomposición exacta de lo que calculó el modelo para este jugador, no una explicación causal.</p>` : ""}
      ${pr ? `<h3>Precedentes: ${pr.n} jugadores parecidos a su edad</h3>
        <p>${pr.sube == null ? "" : `De los que siguieron valuados tres años después, <b>${Math.round(pr.sube * 100)}% valía más</b>; el caso mediano multiplicó su valor por <b>${pr.med}</b>. `}${Math.round((1 - pr.sigue) * 100)}% dejó de estar valuado en ese plazo.</p>
        <div class="tabla-caja"><table class="plana"><thead><tr><th class="izq">Jugador (año)</th><th>Valía entonces</th><th>3 años después</th><th>Máximo posterior</th></tr></thead>
        <tbody>${pr.c.map((x) => `<tr><td class="izq">${esc(x[0])} <span class="tenue">(${x[1]})</span></td><td>${eur(x[2] * 1e3)}</td><td>${x[3] == null ? '<span class="tenue">sin valor</span>' : eur(x[3] * 1e3)}</td><td>${eur(x[4] * 1e3)}</td></tr>`).join("")}</tbody></table></div>
        <p class="nota">Importes llevados a euros de hoy con el índice del mercado. Los cinco más cercanos por posición, edad, valor y tendencia.</p>` : ""}
      ${d.e ? `<h3>Lo que estima EA Sports FC <span class="tenue">(edición vigente en ${d.e[5]})</span></h3>
        <div class="kpis"><div class="kpi"><b>${d.e[0]} → ${d.e[1]}</b><span>media actual → potencial</span></div>
          <div class="kpi"><b>${d.e[2] > 0 ? eur(d.e[2] * 52) : "—"}</b><span>salario anual estimado${d.e[2] > 0 ? ` (${eur(d.e[2])} por semana)` : ""}</span></div>
          <div class="kpi"><b>${d.e[3] > 0 ? eur(d.e[3]) : "—"}</b><span>cláusula de rescisión estimada</span></div>
          <div class="kpi"><b>${d.e[4] > 2000 ? d.e[4] : "—"}</b><span>contrato hasta (según EA)</span></div></div>
        <p class="nota">Son estimaciones del videojuego, no cifras reales de contrato: sirven como referencia de ojeadores y de orden de magnitud salarial. El potencial y el contrato sí entran al modelo.</p>` : ""}
      <div class="dos"><div><h3>Contrato</h3>
        <p>${j.contrato ? `Vence en <b>${fechaYM(+j.contrato.replace("-", ""))}</b>${j.meses != null && j.meses <= 12 && j.meses >= 0 ? ` <span class="baja">(${j.meses} meses)</span>` : ""}` : "Sin fecha de vencimiento en la fuente"}</p>
        ${d.c ? `<p>Cedido por <b>${esc(d.c)}</b></p>` : ""}${d.a ? `<p class="tenue">Agente: ${esc(d.a)}</p>` : ""}</div>
      <div><h3>Rendimiento · 12 meses</h3>${j.min < 0 ? `<p class="tenue">Sin datos de partidos (sólo hay para primeras divisiones).</p>`
        : `<p><b>${j.pj}</b> partidos · <b>${mil(j.min)}</b> min · <b>${j.goles}</b> goles · <b>${j.asist}</b> asistencias</p>`}
        <p class="${j.les24 > 120 ? "baja" : "tenue"}">${j.les24 ? `${j.les24} días de baja por lesión en 24 meses` : "Sin lesiones registradas en 24 meses"}</p></div></div>
      ${d.l ? `<h3>Últimas lesiones</h3><div class="tabla-caja"><table class="plana"><tbody>${[...d.l].reverse().map((x) => `<tr><td class="izq">${fechaYM(+x[0].replace("-", ""))}</td><td class="izq">${esc(x[1])}</td><td>${x[2] < 0 ? "—" : x[2] + " días"}</td></tr>`).join("")}</tbody></table></div>` : ""}
      ${d.t ? `<h3>Últimos fichajes</h3><div class="tabla-caja"><table class="plana"><thead><tr><th class="izq">Fecha</th><th class="izq">De → a</th><th>Pagado</th><th>Valor TM entonces</th></tr></thead>
        <tbody>${[...d.t].reverse().map((x) => `<tr><td class="izq">${fechaYM(+x[0].replace("-", ""))}</td><td class="izq">${esc(x[1])} → ${esc(x[2])}</td><td>${x[5] === 1 ? "cesión" : x[5] === 2 ? "fin de cesión" : x[3] > 0 ? `<b>${eur(x[3])}</b>${x[4] > 0 ? ` <span class="${tono(x[3] / x[4] - 1)}">(${pct(x[3] / x[4] - 1)})</span>` : ""}` : "libre o sin divulgar"}</td><td>${x[4] > 0 ? eur(x[4]) : "—"}</td></tr>`).join("")}</tbody></table></div>` : ""}
      <p class="nota" style="margin-top:18px"><a class="sube" href="https://www.transfermarkt.com/-/profil/spieler/${j.id}" target="_blank" rel="noopener">Ver en Transfermarkt ↗</a></p>`;
    el.scrollTop = 0;
    graficaJugador(j, d);
  }
  function graficaJugador(j, d) {
    const el = d3.select("#g-jugador"), W = el.node().clientWidth, H = 250, m = { t: 12, r: 12, b: 24, l: 50 };
    el.attr("viewBox", `0 0 ${W} ${H}`).attr("height", H);
    const hist = d.h[0].map((ym, i) => [anioDec(ym), d.h[1][i] * 1e3]);
    const Q = d.q || [], t0 = anioDec(j.fecha), n = Math.min(12, Q.length);
    const fut = [{ t: t0, q: [j.valor, j.valor, j.valor, j.valor, j.valor] }].concat(d3.range(1, n + 1).map((h) => ({ t: t0 + h, q: Q[h - 1].map((x) => j.valor * x) })));
    const x = d3.scaleLinear([hist.length ? Math.min(hist[0][0], t0 - 1) : t0 - 1, t0 + Math.max(n, 1)], [m.l, W - m.r]);
    const y = d3.scaleLinear([0, Math.max(d3.max(hist, (p) => p[1]) || 0, d3.max(fut, (p) => p.q[3]) * 1.35 || 0, j.valor) * 1.06], [H - m.b, m.t]);
    el.append("g").attr("class", "eje").attr("transform", `translate(0,${H - m.b})`).call(d3.axisBottom(x).ticks(Math.min(10, W / 60)).tickFormat(d3.format("d")));
    el.append("g").attr("class", "eje").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5).tickFormat(eur));
    const tope = y.domain()[1];                               // el 95% alto puede salirse de escala: se recorta a la vista
    el.append("path").attr("class", "banda b95").attr("d", d3.area().x((p) => x(p.t)).y0((p) => y(p.q[0])).y1((p) => y(Math.min(p.q[4], tope)))(fut));
    el.append("path").attr("class", "banda").attr("d", d3.area().x((p) => x(p.t)).y0((p) => y(p.q[1])).y1((p) => y(p.q[3]))(fut));
    el.append("path").attr("class", "mediana").attr("d", d3.line().x((p) => x(p.t)).y((p) => y(p.q[2]))(fut));
    el.append("path").attr("class", "historia").attr("d", d3.line().x((p) => x(p[0])).y((p) => y(p[1]))(hist));
    el.append("line").attr("class", "hoy").attr("x1", x(t0)).attr("x2", x(t0)).attr("y1", m.t).attr("y2", H - m.b);
    el.append("circle").attr("cx", x(t0)).attr("cy", y(j.valor)).attr("r", 4).attr("fill", "#fff");
    el.append("text").attr("class", "rot").attr("x", x(t0) - 6).attr("y", m.t + 8).attr("text-anchor", "end").text("historia");
    el.append("text").attr("class", "rot").attr("x", x(t0) + 6).attr("y", m.t + 8).text("proyección");
  }

  // ================================================================ eventos globales
  document.addEventListener("click", (e) => {
    const t = e.target;
    const st = t.closest("[data-star]"); if (st) { e.preventDefault(); e.stopPropagation(); alternarLista(+st.dataset.star); if (ruta.v === "lista" && !ruta.j) vistaLista(); return; }
    if (t.closest("[data-cerrar]") || t.id === "velo") return cerrarJ();
    const cs = t.closest("[data-csv]"); if (cs) return csv(cs.dataset.csv);
    const so = t.closest("th[data-sort]");
    if (so) { const caja = so.closest("[data-tabla]"), tb = tablas[caja.dataset.tabla]; tb.asc = tb.orden === so.dataset.sort ? !tb.asc : so.dataset.sort === "nombre"; tb.orden = so.dataset.sort; tb.pag = 0; caja.innerHTML = cuerpoTabla(caja.dataset.tabla); return; }
    const pg = t.closest("[data-pag]"); if (pg) { const caja = pg.closest("[data-tabla]"); tablas[caja.dataset.tabla].pag += +pg.dataset.pag; caja.innerHTML = cuerpoTabla(caja.dataset.tabla); return; }
    const cm = t.closest("[data-comparar]"); if (cm) { const id = +cm.dataset.comparar; comparar.has(id) ? comparar.delete(id) : comparar.size < 6 && comparar.add(id); return vistaLista(); }
    const tb = t.closest("[data-tablero]");
    if (tb) { const T = TABLEROS.find((x) => x.id === tb.dataset.tablero); if (T.fl) fijarFiltros({ ...F, ...T.fl }); tablas.explorar = { orden: T.o, asc: !!T.asc, pag: 0 }; return; }
    const ps = t.closest("[data-pais]"); if (ps) { fijarFiltros({ ...F, pais: ps.dataset.pais, liga: "" }); return; }
    const fj = t.closest("[data-j]"); if (fj) return abrirJ(+fj.dataset.j);
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && ruta.j) cerrarJ(); });

  const caja = $("#buscar"), sug = $("#sugerencias");
  caja.addEventListener("input", () => {
    const q = sinAcentos(caja.value.trim());
    if (q.length < 2) return (sug.hidden = true);
    const js = jugadores.filter((j) => j.clave.includes(q)).sort((a, b) => b.valor - a.valor).slice(0, 9);
    const cs = clubes.filter((c) => c.nivel > 0 && sinAcentos(c.nombre).includes(q)).sort((a, b) => a.nivel - b.nivel).slice(0, 4);
    sug.innerHTML = cs.map((c) => `<li data-ir="#/club/${c.id}"><span>${esc(c.nombre)}</span><small>equipo · ${esc(es(c.pais))}</small></li>`).join("")
      + js.map((j) => `<li data-ir-j="${j.id}"><span>${esc(j.nombre)}</span><small>${esc(j.c.nombre)} · ${eur(j.valor)}</small></li>`).join("")
      || `<li class="tenue">Sin resultados</li>`;
    sug.hidden = false;
  });
  sug.addEventListener("click", (e) => {
    const li = e.target.closest("li");
    if (!li) return;
    sug.hidden = true; caja.value = "";
    if (li.dataset.ir) location.hash = li.dataset.ir; else if (li.dataset.irJ) abrirJ(+li.dataset.irJ);
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".buscador")) sug.hidden = true; });

  // ================================================================ arranque
  $("#n-lista").textContent = lista.size || "";
  $("#pie").innerHTML = `Datos derivados de Transfermarkt (fuentes abiertas) · corte ${meta.corte} · Las proyecciones son estimaciones estadísticas, no precios de traspaso. <a class="sube" href="#/metodo">Metodología y límites</a>`;
  $("#caja-filtros").open = innerWidth > 900;
  aplicarFiltros();
  leerRuta();
  pintar();
})();
