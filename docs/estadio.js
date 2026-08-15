/* ==========================================================================
   Escenario: vista aérea de un estadio, dibujada por código.

   No hay fotos ni imágenes externas. Todo se genera con Canvas a partir de los
   datos reales de cada inmueble —altitud, capacidad, forma de la planta,
   cobertura de techo y el entorno que lo rodea—, así que el sitio sigue pesando
   lo mismo y funciona sin conexión.

   Unidades: metros. La cancha mide 105 × 68 y todo lo demás se mide contra
   ella, que es lo que da la escala correcta entre un estadio y otro.
   ========================================================================== */

const CANCHA_L = 105;
const CANCHA_A = 68;

/* --- paletas de entorno: la topografía alrededor del estadio --- */
const TERRENOS = {
  altiplano: { suelo: "#6d6a52", alt: "#7c7960", calle: "#8b8874", edificio: "#8e8b76", bruma: "#b9c4bf" },
  templado:  { suelo: "#5f6b4b", alt: "#6d7a56", calle: "#87897a", edificio: "#8a8c7c", bruma: "#aebfae" },
  arido:     { suelo: "#8a7457", alt: "#9a8263", calle: "#9d9079", edificio: "#a2947c", bruma: "#d3c4ad" },
  costero:   { suelo: "#8f8467", alt: "#a09472", calle: "#9b9782", edificio: "#a89c80", bruma: "#c6cfc8" },
  calido:    { suelo: "#8f7a5c", alt: "#9e8868", calle: "#9a9080", edificio: "#a09482", bruma: "#cfc3ab" },
};

/* Ruido determinista: mismo estadio, misma ciudad dibujada siempre. */
function semilla(txt) {
  let h = 2166136261;
  for (let i = 0; i < txt.length; i++) {
    h ^= txt.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return () => {
    h += 0x6d2b79f5;
    let t = h;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* Superelipse: n=2 da un óvalo, n alto da un rectángulo redondeado.
   Es lo que permite que el Azteca se vea ovalado y el BBVA rectangular. */
function trazaSuperelipse(ctx, a, b, n, pasos = 160) {
  ctx.beginPath();
  for (let i = 0; i <= pasos; i++) {
    const t = (i / pasos) * Math.PI * 2;
    const c = Math.cos(t), s = Math.sin(t);
    const x = Math.sign(c) * a * Math.pow(Math.abs(c), 2 / n);
    const y = Math.sign(s) * b * Math.pow(Math.abs(s), 2 / n);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  ctx.closePath();
}

function rgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
/* Mezcla dos colores. Sirve para desaturar: las gradas vistas desde el aire
   nunca se ven tan vivas como el uniforme. */
function mezcla(a, b, t) {
  const A = rgb(a), B = rgb(b);
  return `rgb(${A.map((v, i) => Math.round(v + (B[i] - v) * t)).join(",")})`;
}

function aclara(hex, f) {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  const m = (v) => Math.round(f > 0 ? v + (255 - v) * f : v * (1 + f));
  return `rgb(${m(r)},${m(g)},${m(b)})`;
}

class Escenario {
  constructor(lienzo) {
    this.lienzo = lienzo;
    this.ctx = lienzo.getContext("2d");
    this.cam = { x: 0, y: 0, escala: 1, giro: 0 };
    this.estadio = null;
    this.anim = null;
    this.opacidad = 1;
    this.redimensiona();
    addEventListener("resize", () => { this.redimensiona(); this.pinta(); });
  }

  redimensiona() {
    const d = Math.min(devicePixelRatio || 1, 2);
    const { clientWidth: w, clientHeight: h } = this.lienzo;
    this.lienzo.width = Math.max(1, Math.round(w * d));
    this.lienzo.height = Math.max(1, Math.round(h * d));
    this.dpr = d;
    this.w = w;
    this.h = h;
  }

  /* Escala tal que la cancha ocupe una fracción del ancho visible. */
  escalaBase() {
    return (Math.min(this.w, this.h * 1.35) / (CANCHA_L * 2.6));
  }

  pinta() {
    const ctx = this.ctx;
    const e = this.estadio;
    ctx.save();
    ctx.scale(this.dpr, this.dpr);
    ctx.clearRect(0, 0, this.w, this.h);
    if (!e) { ctx.restore(); return; }

    const T = TERRENOS[e.clima] || TERRENOS.templado;
    ctx.fillStyle = T.suelo;
    ctx.fillRect(0, 0, this.w, this.h);

    ctx.globalAlpha = this.opacidad;
    ctx.translate(this.w / 2, this.h / 2);
    ctx.rotate(this.cam.giro);
    const s = this.escalaBase() * this.cam.escala;
    ctx.scale(s, s);
    ctx.translate(-this.cam.x, -this.cam.y);

    this.ciudad(ctx, e, T);
    this.inmueble(ctx, e, T);

    ctx.restore();
    this.vineta(T);
  }

  /* Manzanas y avenidas alrededor: da sensación de altura y de ciudad real. */
  ciudad(ctx, e, T) {
    const r = semilla(e.nombre);
    const alcance = 900;
    ctx.save();
    ctx.fillStyle = T.alt;
    for (let i = 0; i < 26; i++) {
      const x = (r() - 0.5) * alcance * 2;
      const y = (r() - 0.5) * alcance * 2;
      const w = 60 + r() * 190, h = 60 + r() * 190;
      if (Math.abs(x) < 320 && Math.abs(y) < 260) continue;
      ctx.globalAlpha = 0.5 * this.opacidad;
      ctx.fillRect(x, y, w, h);
    }
    ctx.globalAlpha = 0.75 * this.opacidad;
    ctx.strokeStyle = T.calle;
    ctx.lineWidth = 14;
    for (let i = 0; i < 7; i++) {
      const p = (r() - 0.5) * alcance * 1.8;
      ctx.beginPath();
      if (r() > 0.5) { ctx.moveTo(-alcance, p); ctx.lineTo(alcance, p); }
      else { ctx.moveTo(p, -alcance); ctx.lineTo(p, alcance); }
      ctx.stroke();
    }
    ctx.globalAlpha = 0.55 * this.opacidad;
    ctx.fillStyle = T.edificio;
    for (let i = 0; i < 60; i++) {
      const x = (r() - 0.5) * alcance * 2;
      const y = (r() - 0.5) * alcance * 2;
      if (Math.abs(x) < 300 && Math.abs(y) < 240) continue;
      const w = 18 + r() * 46, h = 18 + r() * 46;
      ctx.fillRect(x, y, w, h);
    }
    /* estacionamiento anular */
    ctx.globalAlpha = 0.5 * this.opacidad;
    ctx.fillStyle = T.calle;
    trazaSuperelipse(ctx, e.rx * 1.55, e.ry * 1.55, e.n);
    trazaSuperelipse(ctx, e.rx * 1.04, e.ry * 1.04, e.n);
    ctx.fill("evenodd");
    ctx.restore();
  }

  inmueble(ctx, e, T) {
    const r = semilla(e.nombre + "|estructura");
    const grada = e.rx - e.pitchRx;
    ctx.save();

    /* sombra proyectada sobre el terreno */
    ctx.globalAlpha = 0.32 * this.opacidad;
    ctx.fillStyle = "#000";
    ctx.save();
    ctx.translate(grada * 0.16, grada * 0.22);
    trazaSuperelipse(ctx, e.rx * 1.03, e.ry * 1.03, e.n);
    ctx.fill();
    ctx.restore();
    ctx.globalAlpha = this.opacidad;

    /* fachada exterior */
    ctx.fillStyle = mezcla(e.color1, "#3a3f3c", 0.68);
    trazaSuperelipse(ctx, e.rx, e.ry, e.n);
    ctx.fill();

    /* Gradas por anillos concéntricos, que es como se leen desde el aire:
       tres tiras de butacas separadas por pasillos, no rebanadas de pastel. */
    const base = mezcla(e.color1, "#6a6f6c", 0.5);
    const alterno = mezcla(e.color2, "#6a6f6c", 0.55);
    const anillos = e.capacidad > 45000 ? 3 : 2;
    const dentro = 0.1;                   // deja ver el pasillo interior
    for (let k = 0; k < anillos; k++) {
      const f0 = 1 - dentro - (k * (1 - dentro * 2)) / anillos;
      const f1 = 1 - dentro - ((k + 1) * (1 - dentro * 2)) / anillos;
      const rx0 = e.pitchRx + grada * f0, ry0 = e.pitchRy + grada * f0 * 0.94;
      const rx1 = e.pitchRx + grada * f1, ry1 = e.pitchRy + grada * f1 * 0.94;
      ctx.fillStyle = k === 1 ? alterno : mezcla(base, "#000", k * 0.12);
      trazaSuperelipse(ctx, rx0, ry0, e.n);
      trazaSuperelipse(ctx, rx1, ry1, e.n);
      ctx.fill("evenodd");
      /* pasillo entre anillos */
      ctx.strokeStyle = "rgba(255,255,255,.16)";
      ctx.lineWidth = grada * 0.035;
      trazaSuperelipse(ctx, rx1, ry1, e.n);
      ctx.stroke();
    }

    /* vomitorios: cortes radiales finos, no bloques de color */
    ctx.save();
    ctx.globalAlpha = 0.5 * this.opacidad;
    ctx.strokeStyle = "rgba(15,20,18,.85)";
    ctx.lineWidth = grada * 0.035;
    const cortes = Math.max(18, Math.round(e.capacidad / 2600));
    for (let i = 0; i < cortes; i++) {
      const a = (i / cortes) * Math.PI * 2 + r() * 0.02;
      const c = Math.cos(a), s = Math.sin(a);
      const pr = (fx, fy) => [
        Math.sign(c) * fx * Math.pow(Math.abs(c), 2 / e.n),
        Math.sign(s) * fy * Math.pow(Math.abs(s), 2 / e.n)];
      const [x0, y0] = pr(e.pitchRx + grada * 0.1, (e.pitchRy + grada * 0.1) * 0.99);
      const [x1, y1] = pr(e.rx * 0.985, e.ry * 0.985);
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
    }
    ctx.restore();

    /* voladizo del techo: sombra sobre las butacas de arriba */
    if (e.techo !== "ninguno") {
      const cobertura = e.techo === "total" ? 0.55 : 0.34;
      ctx.globalAlpha = (e.techo === "total" ? 0.78 : 0.6) * this.opacidad;
      ctx.fillStyle = mezcla(e.color1, "#22262a", 0.82);
      trazaSuperelipse(ctx, e.rx, e.ry, e.n);
      trazaSuperelipse(ctx, e.rx - grada * cobertura,
                       e.ry - grada * cobertura * 0.94, e.n);
      ctx.fill("evenodd");
      ctx.globalAlpha = this.opacidad;
    }

    /* perímetro de servicio alrededor de la cancha */
    ctx.fillStyle = mezcla(T.calle, "#2e332f", 0.45);
    trazaSuperelipse(ctx, e.pitchRx, e.pitchRy, Math.min(e.n, 3.2));
    ctx.fill();

    this.cancha(ctx);
    if (e.techo !== "total") this.torres(ctx, e);
    ctx.restore();
  }

  cancha(ctx) {
    const L = CANCHA_L / 2, A = CANCHA_A / 2;
    ctx.save();
    ctx.fillStyle = "#3f7a3d";
    ctx.fillRect(-L - 5, -A - 5, CANCHA_L + 10, CANCHA_A + 10);

    /* franjas de corte */
    const franjas = 12;
    for (let i = 0; i < franjas; i++) {
      ctx.fillStyle = i % 2 ? "#478a44" : "#3d7439";
      ctx.fillRect(-L + (i * CANCHA_L) / franjas, -A, CANCHA_L / franjas, CANCHA_A);
    }

    ctx.strokeStyle = "rgba(255,255,255,.86)";
    ctx.lineWidth = 0.5;
    ctx.strokeRect(-L, -A, CANCHA_L, CANCHA_A);
    ctx.beginPath(); ctx.moveTo(0, -A); ctx.lineTo(0, A); ctx.stroke();
    ctx.beginPath(); ctx.arc(0, 0, 9.15, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(0, 0, 0.9, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255,255,255,.9)"; ctx.fill();

    [-1, 1].forEach((d) => {
      ctx.strokeRect(d * L, -20.16, -d * 16.5, 40.32);   // área grande
      ctx.strokeRect(d * L, -9.16, -d * 5.5, 18.32);     // área chica
      ctx.beginPath(); ctx.arc(d * (L - 11), 0, 0.7, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath();
      ctx.arc(d * (L - 11), 0, 9.15, d > 0 ? Math.PI * 0.72 : -Math.PI * 0.28,
              d > 0 ? Math.PI * 1.28 : Math.PI * 0.28);
      ctx.stroke();
      ctx.fillStyle = "rgba(255,255,255,.75)";
      ctx.fillRect(d * L, -3.66, d * 1.6, 7.32);          // portería
      ctx.fillStyle = "rgba(255,255,255,.9)";
    });
    ctx.restore();
  }

  torres(ctx, e) {
    ctx.save();
    ctx.globalAlpha = 0.9 * this.opacidad;
    const puntos = [[0.72, 0.72], [-0.72, 0.72], [0.72, -0.72], [-0.72, -0.72]];
    puntos.forEach(([fx, fy]) => {
      const x = e.rx * fx * 1.02, y = e.ry * fy * 1.02;
      ctx.fillStyle = "rgba(255,255,255,.5)";
      ctx.beginPath(); ctx.arc(x, y, 5.5, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "rgba(255,255,240,.95)";
      ctx.beginPath(); ctx.arc(x, y, 2.4, 0, Math.PI * 2); ctx.fill();
    });
    ctx.restore();
  }

  /* Bruma en los bordes: da profundidad y despeja el centro para el texto. */
  vineta(T) {
    const ctx = this.ctx;
    ctx.save();
    ctx.scale(this.dpr, this.dpr);
    const g = ctx.createRadialGradient(this.w / 2, this.h * 0.42, Math.min(this.w, this.h) * 0.15,
                                       this.w / 2, this.h * 0.42, Math.max(this.w, this.h) * 0.78);
    g.addColorStop(0, "rgba(0,0,0,0)");
    g.addColorStop(0.55, "rgba(0,0,0,.14)");
    g.addColorStop(1, "rgba(0,0,0,.52)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, this.w, this.h);
    ctx.restore();
  }

  /* ------------------------------------------------------------ animación */

  detener() {
    if (this.anim) cancelAnimationFrame(this.anim);
    this.anim = null;
  }

  anima(destino, ms, suavizado, alTerminar) {
    this.detener();
    const ini = { ...this.cam, opacidad: this.opacidad };
    const t0 = performance.now();
    const paso = (t) => {
      const u = Math.min(1, (t - t0) / ms);
      const k = suavizado(u);
      for (const p of ["x", "y", "escala", "giro"]) {
        if (destino[p] !== undefined) this.cam[p] = ini[p] + (destino[p] - ini[p]) * k;
      }
      if (destino.opacidad !== undefined) {
        this.opacidad = ini.opacidad + (destino.opacidad - ini.opacidad) * k;
      }
      this.pinta();
      if (u < 1) this.anim = requestAnimationFrame(paso);
      else { this.anim = null; if (alTerminar) alTerminar(); }
    };
    this.anim = requestAnimationFrame(paso);
  }

  ponEstadio(e, inmediato) {
    this.estadio = e;
    if (inmediato) this.pinta();
  }
}

const suave = {
  salida: (u) => 1 - Math.pow(1 - u, 3),
  entradaSalida: (u) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2),
};
