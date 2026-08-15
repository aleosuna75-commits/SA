/* ==========================================================================
   Los 16 inmuebles de la Liga MX.

   Cada uno se dibuja a partir de sus datos reales: la capacidad define qué tan
   gruesas son las gradas, la forma de la planta define si se ve ovalado o
   rectangular, el techo define el voladizo, y el entorno define la topografía
   y los colores del terreno alrededor.

   El Estadio Banorte aparece una sola vez aunque lo compartan tres clubes.

   Sobre las cifras: altitud y capacidad son las de referencia habitual de cada
   inmueble. Sólo alimentan el dibujo y la placa informativa —ni el modelo ni
   los pronósticos las usan—, así que un ajuste fino de capacidad no mueve
   ningún número del Cerebro.
   ========================================================================== */

const ESTADIOS = [
  { nombre: "Estadio Banorte", ciudad: "Ciudad de México", equipos: ["América", "Cruz Azul", "Atlante"],
    altitud: 2240, capacidad: 83264, techo: "parcial", forma: "ovalado", clima: "altiplano",
    nota: "El coloso de Santa Úrsula, antes Azteca. Aire a 2,240 m." },

  { nombre: "Estadio Akron", ciudad: "Zapopan", equipos: ["Chivas"],
    altitud: 1560, capacidad: 49850, techo: "parcial", forma: "ovalado", clima: "templado",
    nota: "El volcán de Zapopan, hundido en el terreno." },

  { nombre: "Estadio BBVA", ciudad: "Guadalupe, N.L.", equipos: ["Monterrey"],
    altitud: 500, capacidad: 53500, techo: "total", forma: "rectangular", clima: "calido",
    nota: "El Gigante de Acero, con el Cerro de la Silla al fondo." },

  { nombre: "Estadio Universitario", ciudad: "San Nicolás, N.L.", equipos: ["Tigres"],
    altitud: 500, capacidad: 41615, techo: "parcial", forma: "rectangular", clima: "calido",
    nota: "El Volcán. De los ambientes más cerrados de la liga." },

  { nombre: "Estadio Nemesio Díez", ciudad: "Toluca", equipos: ["Toluca"],
    altitud: 2660, capacidad: 30000, techo: "parcial", forma: "rectangular", clima: "altiplano",
    nota: "La Bombonera. La altura más castigadora del torneo." },

  { nombre: "Estadio Hidalgo", ciudad: "Pachuca", equipos: ["Pachuca"],
    altitud: 2400, capacidad: 30000, techo: "parcial", forma: "rectangular", clima: "altiplano",
    nota: "Altura y viento en la Bella Airosa." },

  { nombre: "Estadio Olímpico Universitario", ciudad: "Ciudad de México", equipos: ["Pumas"],
    altitud: 2280, capacidad: 62000, techo: "ninguno", forma: "ovalado", clima: "altiplano",
    nota: "Pista de atletismo, cráter de lava y pasto natural." },

  { nombre: "Estadio Corregidora", ciudad: "Querétaro", equipos: ["Querétaro"],
    altitud: 1820, capacidad: 33162, techo: "parcial", forma: "ovalado", clima: "altiplano",
    nota: "La Corregidora, sobre una loma al poniente de la ciudad." },

  { nombre: "Estadio Jalisco", ciudad: "Guadalajara", equipos: ["Atlas"],
    altitud: 1560, capacidad: 55020, techo: "parcial", forma: "ovalado", clima: "templado",
    nota: "El coloso de la colonia Independencia." },

  { nombre: "Estadio Caliente", ciudad: "Tijuana", equipos: ["Tijuana"],
    altitud: 30, capacidad: 33333, techo: "parcial", forma: "rectangular", clima: "costero",
    nota: "Pasto sintético y el viaje más largo de la liga." },

  { nombre: "Estadio Cuauhtémoc", ciudad: "Puebla", equipos: ["Puebla"],
    altitud: 2160, capacidad: 51726, techo: "parcial", forma: "ovalado", clima: "altiplano",
    nota: "A la sombra del Popocatépetl." },

  { nombre: "Estadio Victoria", ciudad: "Aguascalientes", equipos: ["Necaxa"],
    altitud: 1880, capacidad: 25000, techo: "parcial", forma: "rectangular", clima: "arido",
    nota: "El más compacto del altiplano." },

  { nombre: "Estadio TSM Corona", ciudad: "Torreón", equipos: ["Santos"],
    altitud: 1120, capacidad: 30000, techo: "parcial", forma: "rectangular", clima: "arido",
    nota: "En pleno desierto lagunero, con calor de 40 grados." },

  { nombre: "Estadio Nou Camp", ciudad: "León", equipos: ["León"],
    altitud: 1800, capacidad: 31297, techo: "parcial", forma: "ovalado", clima: "templado",
    nota: "La casa de La Fiera desde 1967." },

  { nombre: "Estadio Olímpico Benito Juárez", ciudad: "Ciudad Juárez", equipos: ["Juárez"],
    altitud: 1120, capacidad: 19703, techo: "ninguno", forma: "rectangular", clima: "arido",
    nota: "El más pequeño y el más caluroso: desierto de Chihuahua." },

  { nombre: "Estadio Libertad Financiera", ciudad: "San Luis Potosí", equipos: ["Atlético San Luis"],
    altitud: 1860, capacidad: 25709, techo: "parcial", forma: "rectangular", clima: "arido",
    nota: "Antes Alfonso Lastras, en el altiplano potosino." },
];

/* Geometría derivada: de los datos reales a lo que se dibuja. */
function preparaEstadio(e) {
  const eq = (typeof EQUIPOS !== "undefined" && EQUIPOS[e.equipos[0]]) || null;
  // la cancha más el perímetro de servicio
  const pitchRx = 105 / 2 + 13;
  const pitchRy = 68 / 2 + 12;
  // más aforo, gradas más profundas — proporción real contra la cancha
  const grada = 22 + Math.sqrt(e.capacidad) * 0.16;
  // la planta: óvalo, herradura o rectángulo redondeado
  const n = e.forma === "rectangular" ? 4.6 : e.forma === "herradura" ? 3.0 : 2.15;
  return {
    ...e,
    pitchRx, pitchRy, n,
    rx: pitchRx + grada,
    ry: pitchRy + grada * 0.92,
    color1: eq ? eq.c1 : "#2f4a3d",
    color2: eq ? eq.c2 : "#cfd6d1",
  };
}

const ESCENARIOS = ESTADIOS.map(preparaEstadio);
const POR_EQUIPO = {};
ESCENARIOS.forEach((e) => e.equipos.forEach((t) => { POR_EQUIPO[t] = e; }));

/* El Azteca abre siempre: es donde arranca el recorrido. */
const ESTADIO_INICIAL = ESCENARIOS[0];

/* Un estadio al azar, evitando repetir el que ya está en pantalla. */
function estadioAlAzar(excepto) {
  const opciones = ESCENARIOS.filter((e) => e !== excepto);
  return opciones[Math.floor(Math.random() * opciones.length)];
}
