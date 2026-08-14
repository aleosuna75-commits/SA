/* ==========================================================================
   Identidad visual de los equipos.

   ESCUDOS: los escudos de los clubes son marcas registradas y no se
   redistribuyen aquí. Cada equipo se representa con una insignia de monograma
   en sus colores reales, que se lee igual de rápido y no usa material ajeno.

   ¿Quieres los escudos de verdad? Dos pasos:
     1. Coloca los archivos en docs/escudos/ con el nombre del campo `slug` y
        extensión .png (por ejemplo docs/escudos/ame.png).
     2. Agrega ese slug a la lista ESCUDOS de abajo.
   Los que no estén en la lista siguen mostrando su monograma. La lista existe
   para no disparar peticiones a archivos que no están.
   ========================================================================== */

/* Slugs con escudo disponible en docs/escudos/. Vacío = todos con monograma. */
const ESCUDOS = [];

const EQUIPOS = {
  "América":           { slug: "ame", abr: "AME", bg: "#003087", fg: "#FFE600" },
  "Atlas":             { slug: "ats", abr: "ATS", bg: "#A6192E", fg: "#FFFFFF" },
  "Atlante":           { slug: "ate", abr: "ATE", bg: "#0033A0", fg: "#FFFFFF" },
  "Atlético San Luis": { slug: "asl", abr: "ASL", bg: "#C8102E", fg: "#FFFFFF" },
  "Cruz Azul":         { slug: "caz", abr: "CAZ", bg: "#003DA5", fg: "#FFFFFF" },
  "Chivas":            { slug: "chi", abr: "CHI", bg: "#C8102E", fg: "#FFFFFF" },
  "Juárez":            { slug: "jua", abr: "JUA", bg: "#16693B", fg: "#FFFFFF" },
  "León":              { slug: "leo", abr: "LEO", bg: "#0F7A3D", fg: "#FFFFFF" },
  "Monterrey":         { slug: "mty", abr: "MTY", bg: "#16284B", fg: "#FFFFFF" },
  "Necaxa":            { slug: "nec", abr: "NEC", bg: "#D3222A", fg: "#FFFFFF" },
  "Pachuca":           { slug: "pac", abr: "PAC", bg: "#002D62", fg: "#FFFFFF" },
  "Puebla":            { slug: "pue", abr: "PUE", bg: "#005EB8", fg: "#FFFFFF" },
  "Pumas":             { slug: "pum", abr: "PUM", bg: "#14284B", fg: "#D4A017" },
  "Querétaro":         { slug: "qro", abr: "QRO", bg: "#14284B", fg: "#FFFFFF" },
  "Santos":            { slug: "san", abr: "SAN", bg: "#0F7A3D", fg: "#FFFFFF" },
  "Tigres":            { slug: "tig", abr: "TIG", bg: "#F4B223", fg: "#14284B" },
  "Tijuana":           { slug: "tij", abr: "XOL", bg: "#B01E28", fg: "#FFFFFF" },
  "Toluca":            { slug: "tol", abr: "TOL", bg: "#C8102E", fg: "#FFFFFF" },
};

/* Devuelve la insignia del equipo: escudo real si existe, monograma si no. */
function insignia(nombre, tam) {
  const d = EQUIPOS[nombre] || { abr: nombre.slice(0, 3).toUpperCase(),
                                 bg: "#55665f", fg: "#ffffff", slug: null };
  const b = document.createElement("span");
  b.className = "insignia" + (tam ? ` insignia--${tam}` : "");
  b.style.background = d.bg;
  b.style.color = d.fg;
  b.textContent = d.abr;
  b.title = nombre;
  if (d.slug && ESCUDOS.indexOf(d.slug) !== -1) {
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
