/* ==========================================================================
   Los 16 inmuebles de la Liga MX.

   Cada uno se dibuja a partir de sus datos reales: la capacidad define qué tan
   profundas son las gradas y cuántos anillos tiene, la forma de la planta
   define si se ve ovalado o rectangular, el techo define el voladizo, y el
   entorno define la topografía y los colores del terreno alrededor.

   El Estadio Banorte aparece una sola vez aunque lo compartan tres clubes.

   PROCEDENCIA: datos verificados contra fuentes públicas. Donde las fuentes se
   contradicen queda anotado en `confianza` y en la nota; el caso típico es la
   capacidad, que cambia con cada remodelación y que cada fuente reporta
   distinto. Estas cifras sólo alimentan el dibujo y la placa informativa: ni el
   modelo ni los pronósticos las usan, así que un aforo corrido por unos
   cientos de lugares no mueve ningún número del Cerebro.
   ========================================================================== */

const ESTADIOS = [
  { nombre: "Estadio Banorte", ciudad: "Ciudad de México", equipos: ["América", "Cruz Azul", "Atlante"],
    altitud: 2240, capacidad: 87523, techo: "parcial", forma: "ovalado", clima: "altiplano",
    confianza: "alta",
    nota: "Ex Azteca. Reabrió en marzo de 2026 tras la remodelación; el único que comparten tres clubes." },

  { nombre: "Estadio Akron", ciudad: "Zapopan", equipos: ["Chivas"],
    altitud: 1670, capacidad: 46355, techo: "parcial", forma: "ovalado", clima: "templado",
    confianza: "media",
    nota: "Berma de pasto que emula un volcán, con la cubierta flotando como nube." },

  { nombre: "Estadio BBVA", ciudad: "Guadalupe, N.L.", equipos: ["Monterrey"],
    altitud: 500, capacidad: 53500, techo: "parcial", forma: "rectangular", clima: "arido",
    confianza: "media",
    nota: "El Gigante de Acero: la grada sur baja a propósito para enmarcar el Cerro de la Silla." },

  { nombre: "Estadio Universitario", ciudad: "San Nicolás, N.L.", equipos: ["Tigres"],
    altitud: 515, capacidad: 41886, techo: "ninguno", forma: "ovalado", clima: "arido",
    confianza: "media",
    nota: "El Volcán: tazón de concreto continuo, gradas empinadas y ni un metro de techo." },

  { nombre: "Estadio Nemesio Díez", ciudad: "Toluca", equipos: ["Toluca"],
    altitud: 2670, capacidad: 30000, techo: "total", forma: "rectangular", clima: "altiplano",
    confianza: "alta",
    nota: "La Bombonera, el más alto de la liga. Las cuatro tribunas techadas con una trabe de 115 m." },

  { nombre: "Estadio Hidalgo", ciudad: "Pachuca", equipos: ["Pachuca"],
    altitud: 2390, capacidad: 25922, techo: "parcial", forma: "ovalado", clima: "altiplano",
    confianza: "media",
    nota: "El Huracán, por los vientos de Pachuca. Techo sólo en las tribunas laterales." },

  { nombre: "Estadio Olímpico Universitario", ciudad: "Ciudad de México", equipos: ["Pumas"],
    altitud: 2292, capacidad: 58445, techo: "ninguno", forma: "ovalado", clima: "altiplano",
    confianza: "alta",
    nota: "Cuenco elíptico hundido en la lava del Pedregal. Sede olímpica en 1968." },

  { nombre: "Estadio La Corregidora", ciudad: "Querétaro", equipos: ["Querétaro"],
    altitud: 1875, capacidad: 34107, techo: "ninguno", forma: "ovalado", clima: "altiplano",
    confianza: "media",
    nota: "El Coloso del Cimatario: óvalo de tres niveles completamente cerrados." },

  { nombre: "Estadio Jalisco", ciudad: "Guadalajara", equipos: ["Atlas"],
    altitud: 1527, capacidad: 55020, techo: "parcial", forma: "ovalado", clima: "templado",
    confianza: "media",
    nota: "Anillo de lámina de 1970 que cubre la tribuna alta en todo el contorno." },

  { nombre: "Estadio Caliente", ciudad: "Tijuana", equipos: ["Tijuana"],
    altitud: 65, capacidad: 27333, techo: "parcial", forma: "rectangular", clima: "costero",
    confianza: "media",
    nota: "El único con pasto sintético, y aún sin terminar: sólo la tribuna poniente tiene techo." },

  { nombre: "Estadio Cuauhtémoc", ciudad: "Puebla", equipos: ["Puebla"],
    altitud: 2160, capacidad: 51726, techo: "parcial", forma: "ovalado", clima: "altiplano",
    confianza: "alta",
    nota: "De Ramírez Vázquez, sede en 1970 y 1986. El ETFE azul y blanco es fachada, no cubierta." },

  { nombre: "Estadio Victoria", ciudad: "Aguascalientes", equipos: ["Necaxa"],
    altitud: 1885, capacidad: 23851, techo: "parcial", forma: "ovalado", clima: "altiplano",
    confianza: "media",
    nota: "Tazón girado en diagonal, con velaria ondulada salvo en la cabecera sur." },

  { nombre: "Estadio Corona", ciudad: "Torreón", equipos: ["Santos"],
    altitud: 1120, capacidad: 30000, techo: "parcial", forma: "ovalado", clima: "arido",
    confianza: "alta",
    nota: "El Templo del Desierto: un solo nivel continuo en pleno Desierto Chihuahuense." },

  { nombre: "Estadio León", ciudad: "León", equipos: ["León"],
    altitud: 1802, capacidad: 31297, techo: "parcial", forma: "ovalado", clima: "altiplano",
    confianza: "baja",
    nota: "Le dicen Nou Camp desde 1967, aunque nunca fue nombre oficial. Aforo en disputa." },

  { nombre: "Estadio Olímpico Benito Juárez", ciudad: "Ciudad Juárez", equipos: ["Juárez"],
    altitud: 1125, capacidad: 19703, techo: "parcial", forma: "ovalado", clima: "arido",
    confianza: "baja",
    nota: "El aforo más chico de la liga y todavía con pista de atletismo. Cifras en disputa." },

  { nombre: "Estadio Libertad Financiera", ciudad: "San Luis Potosí", equipos: ["Atlético San Luis"],
    altitud: 1860, capacidad: 25709, techo: "ninguno", forma: "ovalado", clima: "altiplano",
    confianza: "media",
    nota: "Ex Alfonso Lastras. Le dicen el hoyo: hundido bajo el nivel de calle, sin anillo superior." },
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
