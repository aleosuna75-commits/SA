/* Mercado: mapa + buscador + proyección. Todo se calcula en el navegador a partir de datos/*.json */
(async function () {
  const [meta, crudos, clubes, ligas, perfiles, mundo] = await Promise.all(
    ["datos/meta.json", "datos/jugadores.json", "datos/clubes.json", "datos/ligas.json", "datos/perfiles.json",
     "lib/countries-50m.json"].map((u) => fetch(u).then((r) => r.json())));

  // ---------------------------------------------------------------- catálogos
  const POS = ["Portero", "Defensa", "Medio", "Delantero"];
  const ETIQUETAS = [["Estrella", 60e6], ["Élite", 25e6], ["Cumplidor", 8e6], ["Regular", 2e6], ["De rol", 0]];
  const PAIS_ES = { Austria: "Austria", Argentina: "Argentina", Australia: "Australia", Belgium: "Bélgica",
    Brazil: "Brasil", Switzerland: "Suiza", Denmark: "Dinamarca", Spain: "España", France: "Francia",
    England: "Inglaterra", Greece: "Grecia", Italy: "Italia", Japan: "Japón", Croatia: "Croacia",
    Germany: "Alemania", Mexico: "México", "United States": "Estados Unidos", Netherlands: "Países Bajos",
    Norway: "Noruega", Poland: "Polonia", Portugal: "Portugal", Romania: "Rumania", "Korea, South": "Corea del Sur",
    Russia: "Rusia", "Saudi Arabia": "Arabia Saudita", Scotland: "Escocia", Sweden: "Suecia", Serbia: "Serbia",
    "Türkiye": "Turquía", "Czech Republic": "Chequia", Ukraine: "Ucrania" };
  // nombre del país en la base -> nombre en el mapa (Inglaterra y Escocia comparten polígono)
  const EN_MAPA = { England: "United Kingdom", Scotland: "United Kingdom", "United States": "United States of America",
    "Korea, South": "South Korea", "Türkiye": "Turkey", "Czech Republic": "Czechia" };
  const REGION = { Argentina: "América", Brazil: "América", Mexico: "América", "United States": "América",
    Japan: "Asia y Oceanía", "Korea, South": "Asia y Oceanía", "Saudi Arabia": "Asia y Oceanía", Australia: "Asia y Oceanía" };
  const region = (p) => REGION[p] || "Europa";
  const enMapa = (p) => EN_MAPA[p] || p;
  const paisEs = (p) => PAIS_ES[p] || p;

  const club = new Map(clubes.map((c) => [c.id, c]));
  const logBins = meta.bins.map(Math.log);

  // ---------------------------------------------------------------- modelo en el cliente
  function perfilDe(j) {
    if (j.edad >= meta.edad_max) return null;
    const lx = Math.log(j.valor);
    let b = 0;
    for (let i = 1; i < logBins.length; i++) if (Math.abs(logBins[i] - lx) < Math.abs(logBins[b] - lx)) b = i;
    return perfiles[`${j.pos}_${Math.max(j.edad, meta.edad_min)}_${b}`] || null;
  }
  const etiquetaDe = (pico) => ETIQUETAS.findIndex((e) => pico >= e[1]);

  const jugadores = crudos.map((r) => {
    const j = { id: r[0], nombre: r[1], club: r[2], pos: r[3], subpos: r[4], edad: r[5], pais: r[6], valor: r[7],
      maxHist: r[8], pj: r[9], min: r[10], goles: r[11], asist: r[12], contrato: r[13] };
    const c = club.get(j.club);
    j.liga = c.liga; j.paisLiga = ligas[c.liga].pais;
    j.p = perfilDe(j);
    j.pico = Math.max(j.maxHist, j.p ? j.valor * j.p.pico[0] : 0);       // máximo de carrera esperado (mediana)
    j.techo = Math.max(j.maxHist, j.p ? j.valor * j.p.pico[1] : 0);      // escenario optimista (p90)
    j.v3 = j.p && j.p.q[2] ? j.valor * j.p.q[2][1] : null;
    j.etq = etiquetaDe(j.pico);
    j.clave = sinAcentos(j.nombre);
    return j;
  });
  const porId = new Map(jugadores.map((j) => [j.id, j]));

  // ---------------------------------------------------------------- utilidades
  function sinAcentos(s) { return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
  function esc(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  function eur(v) {
    if (v == null) return "—";
    if (v >= 1e9) return "€" + (v / 1e9).toFixed(2) + "B";
    if (v >= 1e6) return "€" + (v / 1e6).toFixed(v >= 1e7 ? 0 : 1) + "M";
    return "€" + Math.round(v / 1e3) + "k";
  }
  const pct = (x) => (x >= 0 ? "+" : "") + Math.round(x * 100) + "%";
  const $ = (s) => document.querySelector(s);

  // ---------------------------------------------------------------- filtros
  const F = { region: "", pais: "", liga: "", pos: "", perfil: "", emin: 16, emax: 45, vmin: 0, orden: "pico" };
  let vista = { tipo: "mundo" };
  let inflacion = 0;

  function opciones(sel, lista) {
    const actual = sel.value;
    sel.length = 1;
    lista.forEach(([v, t]) => sel.add(new Option(t, v)));
    sel.value = lista.some(([v]) => String(v) === actual) ? actual : "";
  }
  const paisesLiga = [...new Set(Object.values(ligas).map((l) => l.pais))].sort((a, b) => paisEs(a).localeCompare(paisEs(b)));
  opciones($("#f-region"), ["América", "Europa", "Asia y Oceanía"].map((r) => [r, r]));
  opciones($("#f-pos"), POS.map((p, i) => [i, p]));
  opciones($("#f-perfil"), ETIQUETAS.map((e, i) => [i, e[0]]));
  function refrescarCascada() {
    opciones($("#f-pais"), paisesLiga.filter((p) => !F.region || region(p) === F.region).map((p) => [p, paisEs(p)]));
    F.pais = $("#f-pais").value;
    opciones($("#f-liga"), Object.entries(ligas)
      .filter(([, l]) => (!F.region || region(l.pais) === F.region) && (!F.pais || l.pais === F.pais))
      .sort((a, b) => paisEs(a[1].pais).localeCompare(paisEs(b[1].pais)))
      .map(([k, l]) => [k, `${paisEs(l.pais)} · ${l.nombre}`]));
    F.liga = $("#f-liga").value;
  }
  refrescarCascada();

  function pasa(j) {
    return (!F.region || region(j.paisLiga) === F.region) && (!F.pais || j.paisLiga === F.pais)
      && (!F.liga || j.liga === F.liga) && (F.pos === "" || j.pos === +F.pos)
      && (F.perfil === "" || j.etq === +F.perfil) && j.edad >= F.emin && j.edad <= F.emax && j.valor >= F.vmin;
  }
  const ORDEN = {
    pico: (a, b) => b.pico - a.pico,
    valor: (a, b) => b.valor - a.valor,
    alza: (a, b) => (b.v3 ? b.v3 / b.valor : 0) - (a.v3 ? a.v3 / a.valor : 0),
  };
  let filtrados = [];

  const ids = { region: "#f-region", pais: "#f-pais", liga: "#f-liga", pos: "#f-pos", perfil: "#f-perfil",
    emin: "#f-emin", emax: "#f-emax", vmin: "#f-vmin", orden: "#f-orden" };
  Object.entries(ids).forEach(([k, s]) => $(s).addEventListener("change", (e) => {
    F[k] = ["emin", "emax", "vmin"].includes(k) ? +e.target.value || 0 : e.target.value;
    if (k === "region" || k === "pais") refrescarCascada();
    actualizar();
  }));
  $("#limpiar").addEventListener("click", () => {
    Object.assign(F, { region: "", pais: "", liga: "", pos: "", perfil: "", emin: 16, emax: 45, vmin: 0 });
    Object.entries(ids).forEach(([k, s]) => { if (k !== "orden") $(s).value = F[k]; });
    refrescarCascada();
    ir({ tipo: "mundo" });
    actualizar();
  });

  // ---------------------------------------------------------------- mapa
  const svg = d3.select("#mapa svg");
  const g = svg.append("g");
  const geo = topojson.feature(mundo, mundo.objects.countries).features.filter((f) => f.properties.name !== "Antarctica");
  const proyeccion = d3.geoNaturalEarth1();
  const trazo = d3.geoPath(proyeccion);
  const zoom = d3.zoom().scaleExtent([1, 40]).on("zoom", (e) => g.attr("transform", e.transform));
  svg.call(zoom);
  const paisesConLiga = new Set(paisesLiga.map(enMapa));
  const formas = g.selectAll("path").data(geo).join("path")
    .attr("class", (d) => "pais" + (paisesConLiga.has(d.properties.name) ? " con-datos" : ""))
    .on("click", (e, d) => { if (paisesConLiga.has(d.properties.name)) ir({ tipo: "pais", mapa: d.properties.name }); });
  formas.append("title");

  function ajustarMapa() {
    const { width, height } = svg.node().getBoundingClientRect();
    proyeccion.fitExtent([[8, 8], [width - 8, height - 28]], { type: "FeatureCollection", features: geo });
    formas.attr("d", trazo);
    enfocar();
  }
  function enfocar() {
    const { width, height } = svg.node().getBoundingClientRect();
    const f = vista.mapa && geo.find((d) => d.properties.name === vista.mapa);
    formas.classed("activo", (d) => d.properties.name === vista.mapa);
    if (!f) return svg.transition().duration(600).call(zoom.transform, d3.zoomIdentity);
    // el territorio principal: el polígono más grande (evita que EUA o Francia hagan zoom al planeta)
    let principal = f;
    if (f.geometry.type === "MultiPolygon") {
      const mayor = f.geometry.coordinates.map((c) => ({ type: "Polygon", coordinates: c }))
        .sort((a, b) => d3.geoArea(b) - d3.geoArea(a))[0];
      principal = { type: "Feature", geometry: mayor };
    }
    const [[x0, y0], [x1, y1]] = trazo.bounds(principal);
    const k = Math.min(30, 0.8 / Math.max((x1 - x0) / width, (y1 - y0) / height));
    svg.transition().duration(700).call(zoom.transform,
      d3.zoomIdentity.translate(width / 2, height / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2));
  }
  $("#z-mas").onclick = () => svg.transition().call(zoom.scaleBy, 1.6);
  $("#z-menos").onclick = () => svg.transition().call(zoom.scaleBy, 1 / 1.6);
  $("#z-mundo").onclick = () => ir({ tipo: "mundo" });
  window.addEventListener("resize", ajustarMapa);

  function pintarMapa() {
    const total = d3.rollup(filtrados, (v) => d3.sum(v, (j) => j.valor), (j) => enMapa(j.paisLiga));
    const cuenta = d3.rollup(filtrados, (v) => v.length, (j) => enMapa(j.paisLiga));
    const color = d3.scaleSequentialLog(d3.interpolateRgb("#27496d", "#4cc38a"))
      .domain([Math.max(1e6, d3.min(total.values()) || 1e6), Math.max(2e6, d3.max(total.values()) || 2e6)]);
    formas.style("fill", (d) => (total.get(d.properties.name) ? color(total.get(d.properties.name)) : null));
    formas.select("title").text((d) => {
      const n = d.properties.name;
      return total.get(n) ? `${n}: ${cuenta.get(n)} jugadores · ${eur(total.get(n))}` : n;
    });
  }

  // ---------------------------------------------------------------- panel
  const panel = $("#panel");
  function ir(v) { vista = v; enfocar(); pintarPanel(); if (innerWidth <= 860 && v.tipo !== "mundo") panel.scrollIntoView({ behavior: "smooth" }); }

  function filaJugador(j) {
    const c = club.get(j.club);
    const alza = j.v3 ? j.v3 / j.valor - 1 : null;
    return `<div class="fila" data-jugador="${j.id}">
      <span class="nombre">${esc(j.nombre)} <span class="etiqueta e${j.etq}">${ETIQUETAS[j.etq][0]}</span></span>
      <span class="sub">${POS[j.pos]} · ${j.edad} años · ${esc(c.nombre)}</span>
      <span class="num">${eur(j.valor)}<small>máx. ${eur(j.pico)}${alza == null ? "" : ` · <span class="${alza >= 0 ? "sube" : "baja"}">${pct(alza)} 3a</span>`}</small></span>
    </div>`;
  }
  function migas(partes) {
    return `<nav class="migas">${partes.map(([t, v], i) => (i < partes.length - 1
      ? `<a data-ir='${esc(JSON.stringify(v))}'>${esc(t)}</a><span class="tenue">›</span>` : `<span>${esc(t)}</span>`)).join("")}</nav>`;
  }

  function pintarPanel() {
    const v = vista;
    if (v.tipo === "jugador") return pintarJugador(porId.get(v.id));
    let lista = filtrados, cabecera = "";
    if (v.tipo === "mundo") {
      cabecera = `<h2>Mundo</h2><p class="nota">${lista.length.toLocaleString("es")} jugadores pasan los filtros. Toca un país en el mapa para ver sus equipos.</p>`;
    } else if (v.tipo === "pais") {
      const paises = paisesLiga.filter((p) => enMapa(p) === v.mapa);
      lista = filtrados.filter((j) => paises.includes(j.paisLiga));
      const porClub = d3.rollups(lista, (x) => ({ n: x.length, valor: d3.sum(x, (j) => j.valor), pico: d3.sum(x, (j) => j.pico) }), (j) => j.club)
        .sort((a, b) => b[1].valor - a[1].valor);
      cabecera = migas([["Mundo", { tipo: "mundo" }], [paises.map(paisEs).join(" y "), v]])
        + `<h2>${esc(paises.map(paisEs).join(" y "))}</h2>
           <p class="nota">${[...new Set(lista.map((j) => ligas[j.liga].nombre))].map(esc).join(" · ")} · sólo primera división (ver límites abajo)</p>
           <h3>Equipos (${porClub.length})</h3>`
        + porClub.map(([id, s]) => `<div class="fila" data-club="${id}">
            <span class="nombre">${esc(club.get(id).nombre)}</span>
            <span class="sub">${s.n} jugadores · ${esc(club.get(id).estadio || ligas[club.get(id).liga].nombre)}</span>
            <span class="num">${eur(s.valor)}<small>potencial ${eur(s.pico)}</small></span></div>`).join("")
        + `<h3>Jugadores</h3>`;
    } else if (v.tipo === "club") {
      const c = club.get(v.id), l = ligas[c.liga];
      lista = jugadores.filter((j) => j.club === v.id);
      cabecera = migas([["Mundo", { tipo: "mundo" }], [paisEs(l.pais), { tipo: "pais", mapa: enMapa(l.pais) }], [c.nombre, v]])
        + `<h2>${esc(c.nombre)}</h2><p class="nota">${esc(l.nombre)} · ${esc(c.estadio)}</p>
           <div class="tarjetas">
             <div class="tarjeta"><b>${eur(d3.sum(lista, (j) => j.valor))}</b><span>valor actual de la plantilla</span></div>
             <div class="tarjeta"><b>${eur(d3.sum(lista, (j) => j.v3 ?? j.valor))}</b><span>mediana proyectada a 3 años (euros de hoy)</span></div>
           </div><h3>Plantilla (${lista.length})</h3>`;
    }
    const orden = [...lista].sort(ORDEN[F.orden]);
    panel.innerHTML = cabecera + orden.slice(0, 150).map(filaJugador).join("")
      + (orden.length > 150 ? `<p class="nota">Se muestran 150 de ${orden.length.toLocaleString("es")}. Afina los filtros.</p>` : "")
      + (orden.length ? "" : `<p class="nota">Nadie pasa los filtros actuales.</p>`);
    panel.scrollTop = 0;
  }

  function pintarJugador(j) {
    const c = club.get(j.club), l = ligas[c.liga], p = j.p;
    const f = (h) => Math.pow(1 + inflacion, h);
    const filas = p ? [1, 2, 3, 5, 8, 10].filter((h) => h <= p.q.length).map((h) => {
      const q = p.q[h - 1];
      return `<tr><td>${h} año${h > 1 ? "s" : ""} (${j.edad + h})</td><td>${eur(j.valor * q[0] * f(h))}</td>
        <td><b>${eur(j.valor * q[1] * f(h))}</b></td><td>${eur(j.valor * q[2] * f(h))}</td><td>${Math.round(p.s[h - 1] * 100)}%</td></tr>`;
    }).join("") : "";
    panel.innerHTML = migas([["Mundo", { tipo: "mundo" }], [paisEs(l.pais), { tipo: "pais", mapa: enMapa(l.pais) }],
        [c.nombre, { tipo: "club", id: c.id, mapa: enMapa(l.pais) }], [j.nombre, vista]])
      + `<h2>${esc(j.nombre)} <span class="etiqueta e${j.etq}">${ETIQUETAS[j.etq][0]}</span></h2>
      <p class="nota">${POS[j.pos]}${j.subpos >= 0 ? " (" + esc(meta.subposiciones[j.subpos]) + ")" : ""} · ${j.edad} años ·
        ${j.pais >= 0 ? esc(meta.paises[j.pais]) : ""} · ${esc(c.nombre)}${j.contrato ? " · contrato hasta " + j.contrato : ""}</p>
      <div class="tarjetas">
        <div class="tarjeta"><b>${eur(j.valor)}</b><span>valor actual (${meta.corte})</span></div>
        <div class="tarjeta"><b>${eur(j.pico)}</b><span>valor máximo de carrera esperado${p && j.pico > j.maxHist ? ` · hacia los ${p.edad_pico}` : " · ya lo alcanzó"}</span></div>
        <div class="tarjeta"><b>${eur(j.techo)}</b><span>techo optimista (1 de cada 10)</span></div>
        <div class="tarjeta"><b>${eur(j.maxHist)}</b><span>máximo histórico ya alcanzado</span></div>
      </div>`
      + (p ? `<h3>Proyección de valor</h3>
        <label class="nota">Inflación del mercado <select id="inflacion">
          <option value="0">0% · euros de hoy</option><option value="0.04">4% anual</option>
          <option value="${meta.inflacion_10a}">${(meta.inflacion_10a * 100).toFixed(1)}% · ritmo de los últimos 10 años</option></select></label>
        <svg class="grafica"></svg>
        <table><thead><tr><th>Horizonte (edad)</th><th>Pesimista</th><th>Mediana</th><th>Optimista</th><th>Sigue en el radar</th></tr></thead>
        <tbody>${filas}</tbody></table>
        <p class="nota">Banda = 8 de cada 10 trayectorias de jugadores con la misma posición, edad y nivel de valor.
          «Sigue en el radar» = probabilidad de seguir valuado en una de las ${meta.ligas} ligas cubiertas; los valores son condicionales a eso.</p>
        ${j.valor >= 1e8 ? `<div class="aviso">Por encima de €100M casi no hay historia: aquí el modelo extrapola y vale poco.</div>` : ""}`
        : `<div class="aviso">Con ${j.edad} años queda fuera del rango del modelo (${meta.edad_min}–${meta.edad_max}).</div>`)
      + `<h3>Rendimiento · últimos 12 meses</h3>
      <div class="tarjetas">
        <div class="tarjeta"><b>${j.pj}</b><span>partidos</span></div><div class="tarjeta"><b>${j.min.toLocaleString("es")}</b><span>minutos</span></div>
        <div class="tarjeta"><b>${j.goles}</b><span>goles</span></div><div class="tarjeta"><b>${j.asist}</b><span>asistencias</span></div>
      </div>
      <p class="nota">Los minutos y goles se muestran pero <b>todavía no entran al modelo</b>: la proyección sólo usa posición, edad y valor.</p>`;
    panel.scrollTop = 0;
    if (!p) return;
    const sel = $("#inflacion");
    sel.value = String(inflacion);
    sel.onchange = () => { inflacion = +sel.value; pintarJugador(j); };
    graficar(j, f);
  }

  function graficar(j, f) {
    const el = d3.select(".grafica"), W = el.node().clientWidth, H = 220, m = { t: 8, r: 10, b: 22, l: 46 };
    const pts = [{ e: j.edad, q: [1, 1, 1] }].concat(j.p.q.map((q, i) => ({ e: j.edad + i + 1, q: q.map((x) => x * f(i + 1)) })));
    const x = d3.scaleLinear([j.edad, j.edad + j.p.q.length], [m.l, W - m.r]);
    const y = d3.scaleLinear([0, d3.max(pts, (d) => d.q[2]) * j.valor * 1.05], [H - m.b, m.t]);
    el.attr("viewBox", `0 0 ${W} ${H}`).selectAll("*").remove();
    el.append("g").attr("class", "eje").attr("transform", `translate(0,${H - m.b})`).call(d3.axisBottom(x).ticks(Math.min(8, pts.length)).tickFormat((d) => d + " a"));
    el.append("g").attr("class", "eje").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5).tickFormat(eur));
    el.append("path").attr("class", "banda").attr("d", d3.area().x((d) => x(d.e)).y0((d) => y(d.q[0] * j.valor)).y1((d) => y(d.q[2] * j.valor))(pts));
    el.append("path").attr("class", "mediana").attr("d", d3.line().x((d) => x(d.e)).y((d) => y(d.q[1] * j.valor))(pts));
    el.append("circle").attr("cx", x(j.edad)).attr("cy", y(j.valor)).attr("r", 4).attr("fill", "#fff");
  }

  panel.addEventListener("click", (e) => {
    const m = e.target.closest("[data-ir]"), fj = e.target.closest("[data-jugador]"), fc = e.target.closest("[data-club]");
    if (m) ir(JSON.parse(m.dataset.ir));
    else if (fj) { const j = porId.get(+fj.dataset.jugador); ir({ tipo: "jugador", id: j.id, mapa: enMapa(j.paisLiga) }); }
    else if (fc) { const c = club.get(+fc.dataset.club); ir({ tipo: "club", id: c.id, mapa: enMapa(ligas[c.liga].pais) }); }
  });

  // ---------------------------------------------------------------- buscador
  const caja = $("#buscar"), sug = $("#sugerencias");
  caja.addEventListener("input", () => {
    const q = sinAcentos(caja.value.trim());
    if (q.length < 2) return (sug.hidden = true);
    const js = jugadores.filter((j) => j.clave.includes(q)).sort((a, b) => b.valor - a.valor).slice(0, 8);
    const cs = clubes.filter((c) => sinAcentos(c.nombre).includes(q)).slice(0, 4);
    sug.innerHTML = cs.map((c) => `<li data-club="${c.id}"><span>${esc(c.nombre)}</span><span class="tenue">equipo</span></li>`).join("")
      + js.map((j) => `<li data-jugador="${j.id}"><span>${esc(j.nombre)}</span><span class="tenue">${esc(club.get(j.club).nombre)} · ${eur(j.valor)}</span></li>`).join("")
      || `<li class="tenue">Sin resultados (sólo hay primeras divisiones de ${meta.ligas} ligas)</li>`;
    sug.hidden = false;
  });
  sug.addEventListener("click", (e) => {
    const li = e.target.closest("li");
    if (!li || (!li.dataset.jugador && !li.dataset.club)) return;
    sug.hidden = true; caja.value = "";
    if (li.dataset.jugador) { const j = porId.get(+li.dataset.jugador); ir({ tipo: "jugador", id: j.id, mapa: enMapa(j.paisLiga) }); }
    else { const c = club.get(+li.dataset.club); ir({ tipo: "club", id: c.id, mapa: enMapa(ligas[c.liga].pais) }); }
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".buscador")) sug.hidden = true; });

  // ---------------------------------------------------------------- qué tan confiable es
  function pintarConfianza() {
    const bt = meta.backtest, G = { todos: "Todos", sub23: "Menores de 23", "23a28": "23 a 28", "29mas": "29 o más" };
    $("#confianza").innerHTML = `<h2>Qué tan confiable es esto</h2>
      <p>Prueba retrospectiva: el modelo se entrenó sólo con lo conocido a julio de ${bt.origen} y se comparó contra el valor real años después.
      «Error típico» es la mediana de cuánto se desvía la proyección central del valor real. La referencia ingenua es suponer que el valor no cambia.</p>
      <div class="tabla"><table><thead><tr><th>Horizonte</th><th>Grupo</th><th>Jugadores</th><th>Error típico del modelo</th><th>Error típico ingenuo</th><th>Real dentro de la banda (meta 80%)</th></tr></thead>
      <tbody>${bt.filas.map((r) => `<tr><td>${r.horizonte} año${r.horizonte > 1 ? "s" : ""}</td><td>${G[r.grupo]}</td><td>${r.n.toLocaleString("es")}</td>
        <td>${Math.round(r.error_modelo * 100)}%</td><td>${Math.round(r.error_ingenuo * 100)}%</td><td>${Math.round(r.cobertura_p10_p90 * 100)}%</td></tr>`).join("")}</tbody></table></div>
      <h3>Límites que hay que tener presentes</h3>
      <ul>
        <li><b>No son todos los futbolistas del mundo:</b> ${meta.jugadores.toLocaleString("es")} jugadores de la primera división de ${meta.ligas} ligas. No hay segundas divisiones ni el resto de países.</li>
        <li><b>Proyecta la valuación pública de Transfermarkt</b> (una estimación de la comunidad), no precios de traspaso reales.</li>
        <li><b>El modelo sólo ve posición, edad y valor actual.</b> No usa minutos, goles, liga, contrato, lesiones ni mediaticidad: dos jugadores con esos tres datos iguales reciben la misma proyección.</li>
        <li><b>A 1 año casi no mejora a la referencia ingenua</b> y en menores de 23 no la mejora. Su ventaja aparece a 3–5 años, donde aun así el error típico ronda un factor de 2.</li>
        <li><b>Sesgo de supervivencia:</b> las bandas son para quien sigue en las ligas cubiertas; quien desaparece de la base (descenso, retiro, liga menor) no cuenta, y eso infla las medianas.</li>
        <li>El perfil (Estrella ≥ €60M, Élite ≥ €25M, Cumplidor ≥ €8M, Regular ≥ €2M, De rol) es un corte arbitrario sobre el valor máximo de carrera esperado.</li>
      </ul>
      <p class="tenue">Datos: transfermarkt-datasets (CC0), corte ${meta.corte}. Índice del mercado (500 jugadores más caros): ×${meta.indice_mercado.valor.at(-1)} desde ${meta.indice_mercado.anios[0]}.</p>`;
  }

  // ---------------------------------------------------------------- arranque
  function actualizar() {
    filtrados = jugadores.filter(pasa);
    $("#resumen").textContent = `${meta.jugadores.toLocaleString("es")} jugadores · ${meta.clubes} equipos · ${meta.ligas} ligas · corte ${meta.corte}`;
    pintarMapa();
    pintarPanel();
  }
  $("#caja-filtros").open = innerWidth > 860;
  ajustarMapa();
  actualizar();
  pintarConfianza();
})();
