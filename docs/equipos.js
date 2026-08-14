/* ==========================================================================
   Identidad visual de los equipos.

   ESCUDOS REALES: no vienen en el repositorio. No es una postura, es que no
   están disponibles por una vía limpia: los escudos de Liga MX no existen en
   Wikimedia Commons con licencia libre y en Wikipedia son archivos de uso
   legítimo, no redistribuibles. Si tú los consigues, la página los usa: mételos
   en docs/escudos/ y corre `python preparar_escudos.py` (ver ese archivo).

   MIENTRAS TANTO: cada equipo lleva una insignia inspirada en su UNIFORME, no
   en su escudo — rayas rojiblancas para Chivas, rayas amarillo y azul para
   Tigres, azul marino con oro para Pumas. Es diseño propio, se reconoce de un
   vistazo y no copia material ajeno.
   ========================================================================== */

/* Slugs con escudo disponible en docs/escudos/. Lo llena preparar_escudos.py. */
const ESCUDOS = [];

/* patron: solido | rayas (verticales) | mitades (diagonal) */
const EQUIPOS = {
  "América":           { slug: "ame", abr: "AME", patron: "solido",  c1: "#0A2240", c2: "#FFD100", fg: "#FFD100" },
  "Atlas":             { slug: "ats", abr: "ATS", patron: "rayas",   c1: "#A6192E", c2: "#111111", fg: "#FFFFFF" },
  "Atlante":           { slug: "ate", abr: "ATE", patron: "mitades", c1: "#0033A0", c2: "#C8102E", fg: "#FFFFFF" },
  "Atlético San Luis": { slug: "asl", abr: "ASL", patron: "rayas",   c1: "#C8102E", c2: "#0A2240", fg: "#FFFFFF" },
  "Cruz Azul":         { slug: "caz", abr: "CAZ", patron: "solido",  c1: "#003DA5", c2: "#FFFFFF", fg: "#FFFFFF" },
  "Chivas":            { slug: "chi", abr: "CHI", patron: "rayas",   c1: "#C8102E", c2: "#FFFFFF", fg: "#0A2240" },
  "Juárez":            { slug: "jua", abr: "JUA", patron: "mitades", c1: "#16693B", c2: "#111111", fg: "#FFFFFF" },
  "León":              { slug: "leo", abr: "LEO", patron: "solido",  c1: "#0F7A3D", c2: "#FFFFFF", fg: "#FFFFFF" },
  "Monterrey":         { slug: "mty", abr: "MTY", patron: "rayas",   c1: "#16284B", c2: "#FFFFFF", fg: "#16284B" },
  "Necaxa":            { slug: "nec", abr: "NEC", patron: "solido",  c1: "#D3222A", c2: "#FFFFFF", fg: "#FFFFFF" },
  "Pachuca":           { slug: "pac", abr: "PAC", patron: "rayas",   c1: "#0A4D8C", c2: "#FFFFFF", fg: "#0A4D8C" },
  "Puebla":            { slug: "pue", abr: "PUE", patron: "mitades", c1: "#005EB8", c2: "#FFFFFF", fg: "#FFFFFF" },
  "Pumas":             { slug: "pum", abr: "PUM", patron: "solido",  c1: "#14284B", c2: "#D4A017", fg: "#D4A017" },
  "Querétaro":         { slug: "qro", abr: "QRO", patron: "mitades", c1: "#14284B", c2: "#111111", fg: "#FFFFFF" },
  "Santos":            { slug: "san", abr: "SAN", patron: "solido",  c1: "#0F7A3D", c2: "#FFFFFF", fg: "#FFFFFF" },
  "Tigres":            { slug: "tig", abr: "TIG", patron: "rayas",   c1: "#F4B223", c2: "#14284B", fg: "#14284B" },
  "Tijuana":           { slug: "tij", abr: "XOL", patron: "mitades", c1: "#B01E28", c2: "#111111", fg: "#FFFFFF" },
  "Toluca":            { slug: "tol", abr: "TOL", patron: "rayas",   c1: "#C8102E", c2: "#FFFFFF", fg: "#C8102E" },
};

function fondo(d) {
  if (d.patron === "rayas") {
    return `repeating-linear-gradient(90deg, ${d.c1} 0 22%, ${d.c2} 22% 44%)`;
  }
  if (d.patron === "mitades") {
    return `linear-gradient(115deg, ${d.c1} 0 50%, ${d.c2} 50% 100%)`;
  }
  return d.c1;
}

/* Devuelve la insignia del equipo: escudo real si está disponible, insignia
   de uniforme si no. */
function insignia(nombre, tam) {
  const d = EQUIPOS[nombre];
  const b = document.createElement("span");
  b.className = "insignia" + (tam ? ` insignia--${tam}` : "");
  b.title = nombre;
  if (!d) {
    b.style.background = "#55665f";
    b.style.color = "#fff";
    b.appendChild(el2("span", "insignia__abr", nombre.slice(0, 3).toUpperCase()));
    return b;
  }
  b.style.background = fondo(d);
  const disco = el2("span", "insignia__disco");
  disco.style.background = d.patron === "solido" ? "transparent" : "rgba(0,0,0,.55)";
  disco.style.color = d.fg;
  disco.textContent = d.abr;
  b.appendChild(disco);

  if (ESCUDOS.indexOf(d.slug) !== -1) {
    const img = document.createElement("img");
    img.alt = "";
    img.loading = "lazy";
    img.src = `escudos/${d.slug}.png`;
    img.addEventListener("load", () => b.classList.add("insignia--escudo"));
    img.addEventListener("error", () => img.remove());
    b.appendChild(img);
  }
  return b;
}

function el2(t, c, x) {
  const n = document.createElement(t);
  n.className = c;
  if (x != null) n.textContent = x;
  return n;
}
