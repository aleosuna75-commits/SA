/* ==========================================================================
   Cerebro Liga MX 2026 — índice de jornadas, jornada y proyección de campeón
   Este archivo NO calcula probabilidades: sólo formatea lo que el Cerebro
   (Python) ya calculó. La fuente de verdad es el modelo.
   ========================================================================== */

const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const MESES = ["ene", "feb", "mar", "abr", "may", "jun",
               "jul", "ago", "sep", "oct", "nov", "dic"];

const pct = (p, d = 1) => (p * 100).toFixed(d) + "%";
const fecha = (iso) => {
  const [a, m, d] = iso.split("-").map(Number);
  return `${DIAS[new Date(Date.UTC(a, m - 1, d)).getUTCDay()]} ${d} ${MESES[m - 1]}`;
};
const el = (tag, clase, texto) => {
  const n = document.createElement(tag);
  if (clase) n.className = clase;
  if (texto != null) n.textContent = texto;
  return n;
};
const vaciar = (n) => { while (n.firstChild) n.removeChild(n.firstChild); };

const ORIGEN = {
  publicado:    ["Pronóstico sellado antes de jugarse", "sello--ok"],
  reconstruido: ["Reconstruido fuera de muestra", "sello--aviso"],
  vigente:      ["Por jugarse", "sello--vivo"],
  programada:   ["Calendario confirmado", "sello--aviso"],
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
  [p.local, p.visitante].forEach((t, i) => {
    const fila = el("div", "equipo");
    fila.appendChild(insignia(t));
    fila.appendChild(el("span", "equipo__nombre", t));
    eq.appendChild(fila);
    if (i === 0) eq.appendChild(el("div", "marcador__vs", "vs"));
  });
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

/* ------------------------------------------------------------ vista jornada */

function pintaJornada(d) {
  document.getElementById("titulo").textContent = `Jornada ${d.jornada}`;
  document.getElementById("subtitulo").textContent = d.torneo;

  const [txt, clase] = ORIGEN[d.origen] || ORIGEN.vigente;
  const sello = document.getElementById("sello");
  sello.textContent = txt;
  sello.className = "sello " + clase;
  sello.hidden = false;

  const nota = document.getElementById("nota-origen");
  nota.textContent = d.nota_origen || "";
  nota.hidden = !d.nota_origen;

  const res = document.getElementById("resumen");
  vaciar(res);
  const tit = document.getElementById("titulo-resumen");
  if (d.resumen) {
    tit.textContent = "Cómo le fue al modelo";
    const j = d.resumen, malo = j.brier > 0.667;
    [["Aciertos 1X2", `${j.aciertos_1x2}/${j.partidos}`, pct(j.aciertos_1x2 / j.partidos, 0), false],
     ["Marcador exacto", `${j.marcadores_exactos}/${j.partidos}`, "de 9 partidos", false],
     ["Brier", j.brier.toFixed(3), malo ? "peor que el azar (0.667)" : "mejor que el azar (0.667)", malo],
     ["Parlays", `${j.parlays_pegados}/3`, j.parlays_pegados ? "" : "ninguno pegó", j.parlays_pegados === 0],
    ].forEach(([e2, v, n2, m]) => {
      const c = el("div", "dato" + (m ? " dato--malo" : ""));
      c.append(el("div", "dato__etiqueta", e2), el("div", "dato__valor", v),
               el("div", "dato__nota", n2));
      res.appendChild(c);
    });
  } else {
    tit.textContent = "Jornada por jugarse";
    const h = d.modelo.historico;
    [["Partidos", String(d.partidos.length), "aún sin resultado", false],
     ["Calibrado con", h.partidos.toLocaleString("es-MX"), `partidos, hasta ${fecha(h.hasta)}`, false],
     ["Corte", fecha(d.corte_calibracion), "no ve nada posterior", true],
    ].forEach(([e2, v, n2, t]) => {
      const c = el("div", "dato" + (t ? " dato--texto" : ""));
      c.append(el("div", "dato__etiqueta", e2), el("div", "dato__valor", v),
               el("div", "dato__nota", n2));
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

  const h = d.modelo.historico, cr = d.modelo.credibilidad || {};
  document.getElementById("procedencia").innerHTML =
    `Dixon-Coles con corrección ρ = ${d.modelo.rho_dc} sobre la malla exacta de marcadores. ` +
    `Calibrado por máxima verosimilitud con <b>${h.partidos.toLocaleString("es-MX")} partidos reales</b> ` +
    `(${h.desde} a ${h.hasta}), decaimiento temporal ξ = ${d.modelo.xi_decaimiento} por día. ` +
    `Corte de calibración: <b>${d.corte_calibracion}</b> — el modelo no ve ningún partido posterior. ` +
    (cr.activa ? `Credibilidad Z = w³/(w³+${cr.k}³) hacia el prior para equipos con poco histórico. ` : "");
}

/* -------------------------------------------------------------- vista índice */

function pintaIndice(idx, proy, ir) {
  document.getElementById("titulo").textContent = idx.torneo;
  document.getElementById("subtitulo").textContent =
    `${idx.formato.jornadas} jornadas · ${idx.formato.equipos} equipos · ` +
    `clasifican ${idx.formato.clasifican}`;
  document.getElementById("sello").hidden = true;

  /* --- campeón --- */
  const cont = document.getElementById("campeon");
  vaciar(cont);
  if (proy) {
    const max = proy.equipos[0].campeon || 1;
    proy.equipos.slice(0, 8).forEach((t) => {
      const f = el("div", "candidato");
      f.appendChild(insignia(t.equipo, "sm"));
      f.appendChild(el("span", "candidato__nombre", t.equipo));
      const barra = el("div", "candidato__barra");
      const relleno = el("div", "candidato__relleno");
      relleno.style.width = `${Math.max(2, (t.campeon / max) * 100)}%`;
      barra.appendChild(relleno);
      f.appendChild(barra);
      f.appendChild(el("span", "candidato__pct", pct(t.campeon)));
      f.appendChild(el("span", "candidato__extra", `clasifica ${pct(t.clasifica, 0)}`));
      cont.appendChild(f);
    });
    document.getElementById("campeon-nota").textContent =
      `${proy.simulaciones.toLocaleString("es-MX")} simulaciones del torneo completo ` +
      `(${proy.partidos_restantes} partidos por jugar más la liguilla). ${proy.supuesto}`;
  }

  /* --- las 17 jornadas --- */
  const lista = document.getElementById("lista-jornadas");
  vaciar(lista);
  idx.jornadas.forEach((j) => {
    const clickable = !!j.archivo;
    const fila = el(clickable ? "button" : "div",
                    "jfila" + (j.jornada === idx.jornada_vigente ? " jfila--vigente" : "")
                            + (clickable ? "" : " jfila--muda"));
    if (clickable) {
      fila.type = "button";
      fila.addEventListener("click", () => ir(j.jornada));
    }
    fila.appendChild(el("span", "jfila__n", `J${j.jornada}`));
    const med = el("span", "jfila__medio");
    med.appendChild(el("span", "jfila__fechas", (j.fechas || "").toLowerCase()));
    const est = j.resumen
      ? `${j.resumen.aciertos_1x2}/${j.resumen.partidos} aciertos · Brier ${j.resumen.brier.toFixed(3)}`
      : (j.estado === "sin_calendario" ? "emparejamientos aún no publicados"
                                       : "pronóstico listo");
    med.appendChild(el("span", "jfila__estado", est));
    fila.appendChild(med);
    if (j.jornada === idx.jornada_vigente) fila.appendChild(el("span", "etiqueta", "vigente"));
    else if (j.resumen) fila.appendChild(el("span", "etiqueta etiqueta--ok", "jugada"));
    lista.appendChild(fila);
  });

  /* --- desempeño --- */
  const ac = document.getElementById("acumulado");
  vaciar(ac);
  const a = idx.desempeno.acumulado;
  if (a.partidos) {
    const malo = a.brier > 0.667;
    [["Aciertos 1X2", `${a.aciertos_1x2}/${a.partidos}`, pct(a.aciertos_1x2 / a.partidos, 0), false],
     ["Marcador exacto", String(a.marcadores_exactos), `de ${a.partidos} partidos`, false],
     ["Brier acumulado", a.brier.toFixed(3), malo ? "peor que el azar" : "mejor que el azar (0.667)", malo],
    ].forEach(([e2, v, n2, m]) => {
      const c = el("div", "dato" + (m ? " dato--malo" : ""));
      c.append(el("div", "dato__etiqueta", e2), el("div", "dato__valor", v),
               el("div", "dato__nota", n2));
      ac.appendChild(c);
    });
  }

  const tb = document.getElementById("historico");
  vaciar(tb);
  idx.desempeno.por_jornada.forEach((h) => {
    const tr = document.createElement("tr");
    [`Jornada ${h.jornada}${h.origen === "reconstruido" ? " *" : ""}`,
     `${h.aciertos_1x2}/${h.partidos}`, String(h.marcadores_exactos),
     h.brier.toFixed(3)].forEach((t) => {
      const td = document.createElement("td");
      td.textContent = t;
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
  if (a.partidos) {
    const tr = document.createElement("tr");
    tr.className = "acumulado";
    ["Acumulado", `${a.aciertos_1x2}/${a.partidos}`, String(a.marcadores_exactos),
     a.brier.toFixed(3)].forEach((t) => {
      const td = document.createElement("td");
      td.textContent = t;
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  }
  document.getElementById("convencion").textContent = idx.desempeno.convencion_brier;
  document.getElementById("procedencia").innerHTML =
    "Modelo Dixon-Coles calibrado por máxima verosimilitud sobre el histórico real de Liga MX, " +
    "con decaimiento temporal y credibilidad para equipos con poco histórico. Cada jornada se " +
    "calibra <b>sólo con partidos anteriores a su fecha</b>, así que ningún pronóstico ve " +
    "resultados posteriores a sí mismo.";
}

/* --------------------------------------------------------- escenario aéreo */

const MENOS_MOVIMIENTO =
  matchMedia("(prefers-reduced-motion: reduce)").matches;

/* La cámara descansa un poco atrás para que el inmueble se vea alrededor del
   contenido, no sólo el círculo central. */
/* En reposo la cámara queda lo bastante cerca para que las gradas llenen los
   costados; si se aleja más, el inmueble queda tapado por la columna de
   contenido y el fondo se pierde. */
const REPOSO = { x: 0, y: 0, escala: 1.18, giro: 0 };

const escena = new Escenario(document.getElementById("escenario"));
let sedeActual = null;

let relojSede = null;
function pintaSede(e) {
  const placa = document.getElementById("sede");
  document.getElementById("sede-nombre").textContent = e.nombre;
  document.getElementById("sede-datos").textContent =
    `${e.ciudad} · ${e.altitud.toLocaleString("es-MX")} m · ` +
    `${e.capacidad.toLocaleString("es-MX")} lugares`;
  placa.classList.remove("guardada");
  clearTimeout(relojSede);
  relojSede = setTimeout(() => placa.classList.add("guardada"), 4200);
}

/* Entrada: toma aérea alta que desciende hasta el círculo central del Azteca.
   De ahí emerge el índice. */
function entrada(alAsentar) {
  sedeActual = ESTADIO_INICIAL;
  escena.ponEstadio(sedeActual, true);
  pintaSede(sedeActual);

  if (MENOS_MOVIMIENTO) {
    escena.cam = { ...REPOSO };
    escena.pinta();
    document.body.classList.add("asentado");
    alAsentar();
    return;
  }

  escena.cam = { x: 70, y: -46, escala: 0.11, giro: -0.55 };
  escena.opacidad = 1;
  escena.pinta();

  // primero baja al centro de la cancha...
  escena.anima({ x: 0, y: 0, escala: 1.9, giro: 0 }, 2600, suave.salida, () => {
    // ...y retrocede lo justo para dejar sitio al contenido
    escena.anima(REPOSO, 900, suave.entradaSalida);
  });

  setTimeout(() => {
    document.body.classList.add("asentado");
    alAsentar();
  }, 1750);
}

/* Cambio de jornada: vuelo a otro estadio de la liga. */
function vuelaAOtroEstadio() {
  const destino = estadioAlAzar(sedeActual);
  sedeActual = destino;

  if (MENOS_MOVIMIENTO) {
    escena.ponEstadio(destino, true);
    pintaSede(destino);
    return;
  }
  const giro = (Math.random() - 0.5) * 0.7;
  document.body.classList.add("volando");
  escena.anima({ escala: 0.34, giro, opacidad: 0.2 }, 700, suave.entradaSalida, () => {
    escena.ponEstadio(destino, false);
    pintaSede(destino);
    escena.cam.giro = -giro;
    escena.anima({ ...REPOSO, opacidad: 1 }, 1250, suave.salida, () => {
      document.body.classList.remove("volando");
    });
  });
}

/* ------------------------------------------------------------------ arranque */

const VISTA_I = document.getElementById("vista-indice");
const VISTA_J = document.getElementById("vista-jornada");
const VOLVER = document.getElementById("volver");

function arranca(cargarIndice, cargarJornada, cargarProy, autorefresco) {
  let idx = null, proy = null, actual = null;

  const alIndice = () => {
    actual = null;
    VISTA_J.hidden = true; VISTA_I.hidden = false; VOLVER.hidden = true;
    pintaIndice(idx, proy, irJornada);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const irJornada = (n, mismoLugar) => {
    const cambia = actual !== n;
    actual = n;
    if (cambia && !mismoLugar) vuelaAOtroEstadio();
    Promise.resolve(cargarJornada(n)).then((d) => {
      VISTA_I.hidden = true; VISTA_J.hidden = false; VOLVER.hidden = false;
      pintaJornada(d);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  };
  VOLVER.addEventListener("click", alIndice);

  const sello = (i) => {
    document.getElementById("actualizado").textContent =
      (i.actualizado || "").replace("T", " ").slice(0, 16) || "—";
  };

  Promise.all([cargarIndice(), cargarProy()]).then(([i, p]) => {
    idx = i; proy = p; sello(i);
    pintaIndice(idx, proy, irJornada);
    entrada(() => { VISTA_J.hidden = true; VISTA_I.hidden = false; VOLVER.hidden = true; });

    /* Autoactualización: revisa el índice cada minuto y sólo repinta si el
       generador publicó algo nuevo. Es lo que hace que, al subir resultados,
       las pantallas ya abiertas se enteren solas. */
    if (autorefresco) {
      setInterval(() => {
        cargarIndice().then((nuevo) => {
          if (!nuevo || nuevo.actualizado === idx.actualizado) return;
          idx = nuevo; sello(nuevo);
          cargarProy().then((np) => { proy = np; });
          if (actual === null) pintaIndice(idx, proy, irJornada);
          else irJornada(actual, true);
        }).catch(() => {});
      }, 60000);
    }
  });
}

if (typeof DATOS !== "undefined") {
  arranca(() => DATOS.indice, (n) => DATOS.jornadas[String(n)], () => DATOS.proyeccion, false);
} else {
  const j = (u) => fetch(u, { cache: "no-cache" }).then((r) => r.json());
  arranca(() => j("datos/indice.json"),
          (n) => j(`datos/j${String(n).padStart(2, "0")}.json`),
          () => j("datos/proyeccion.json").catch(() => null),
          true);
}
