/* ============================================================
   Viaje SoCal 2026 — datos del viaje
   Zona horaria de referencia: America/Los_Angeles (PDT, UTC-7)
   CDMX es UTC-6 => California va 1 HORA ATRAS que CDMX.
   ============================================================ */

const TRIP = {
  nombre: 'Viaje SoCal 2026',
  lema: 'CDMX → Tijuana → San Diego → Anaheim → LA',
  inicio: '2026-09-08T05:32:00-06:00', // despegue AICM (hora CDMX)
  fin:    '2026-09-14T23:59:00-07:00',
  tz: 'America/Los_Angeles',
  monedaBase: 'USD',
  tipoCambioDefault: 18.5
};

/* ---------- ALERTAS: conflictos reales detectados ---------- */
const ALERTAS = [
  {
    nivel: 'alto',
    dia: 'general',
    titulo: 'Al salir del parque, NO pidas el Uber en la zona oficial',
    detalle: 'El punto oficial de Uber y Lyft sobre Harbor Blvd es chico para el tamaño del parque. Al cierre, la fila de choferes esperando entrar se desborda sobre la avenida: tú esperas y tu carro no puede llegar. Es el peor momento del día y coincide con el pico de tarifa.',
    accion: 'Sal caminando a Harbor Blvd, cruza al McDonald\'s de enfrente y pide desde ahí. El chofer te recoge en calle normal, sin fila, y de paso sales del punto donde el surge pega más fuerte. Para la LLEGADA sí usa el punto oficial: en la mañana no hay fila y te deja más cerca.'
  },
  {
    nivel: 'medio',
    dia: 'general',
    titulo: 'Ya nadie tiene entrada anticipada, y eso te conviene',
    detalle: 'Disneyland eliminó el Early Theme Park Entry el 5 de enero de 2026. Antes, los huéspedes de los hoteles Disney entraban 30 minutos antes y te ganaban las primeras atracciones. Eso se acabó para todos. A cambio les dan una Lightning Lane gratis por estancia, que los Good Neighbor no reciben.',
    accion: 'Tu rope drop ahora vale tanto como el de cualquiera. A las 8:00 entran todos al mismo tiempo: el que llegó a las 7:30 a la explanada gana, sin importar dónde durmió.'
  },
  {
    nivel: 'critico',
    dia: 'mie-9',
    titulo: 'Dodgers y Disneyland el mismo día no caben completos',
    detalle: 'El 9 de septiembre los Dodgers reciben a los Rojos de Cincinnati a las 19:10 en Dodger Stadium. De Anaheim al estadio son ~74 km que en hora pico se convierten en 1h15 a 2h de manejo. Si quieres estar en tu asiento para el primer lanzamiento, tienes que salir de Disneyland a las 15:45 y del estacionamiento a las 16:15, sin excepción.',
    accion: 'Trata el 9 como MEDIO DÍA de Disneyland: rope drop a las 8:00 y salida a las 15:45. Son casi 8 horas útiles si llegas a la apertura: alcanza perfectamente si no te duermes en la mañana.'
  },
  {
    nivel: 'critico',
    dia: 'mar-8',
    titulo: 'La ventana de compras del día 8 es de 85 minutos, no de una tarde',
    detalle: 'Entre recoger el Turo en San Diego (~10:15), manejar a Anaheim (1h40–2h10), dejar maletas y llegar a la entrada de DCA a las 14:45, sólo quedan de 12:15 a 13:40 libres. Target, Ross y Marshalls en un mismo centro comercial es la única forma de que quepan los tres.',
    accion: 'Compra en el clúster de Buena Park, justo sobre la I-5 y a 15 min de Disneyland. Pon alarma de HORA LÍMITE a la 13:40 y respétala aunque quede carrito a medias.'
  },
  {
    nivel: 'alto',
    dia: 'jue-10',
    titulo: 'Halloween Horror Nights puede cerrar Universal temprano el día 10 y el 13',
    detalle: 'HHN 2026 corre en noches selectas del 3 de septiembre al 1 de noviembre y arranca a las 19:00. En noches de HHN el parque diurno cierra antes (típicamente entre 17:00 y 19:00) y desalojan a quien no traiga boleto del evento. Además, parte del backlot se cierra durante el día para montar las casas.',
    accion: 'Confirma en la app de Universal si el 10 y el 13 son noches de HHN. Si lo son, tu día en Universal termina a las 17:00: hay que hacer rope drop obligatorio y bajar al Lower Lot primero.'
  },
  {
    nivel: 'alto',
    dia: 'mar-8',
    titulo: 'California Adventure cierra al público a las 18:00 en noches de Oogie Boogie',
    detalle: 'Tu boleto de Oogie Boogie Bash te deja entrar desde las 15:00 y no requiere reservación de parque. A las 18:00 sacan a todo el que no trae boleto de fiesta y arranca el evento hasta las 23:00. Eso significa que de 15:00 a 18:00 el parque se está VACIANDO: es tu mejor ventana de atracciones grandes del viaje.',
    accion: 'Usa 15:00–18:00 para Radiator Springs Racers, Web Slingers e Incredicoaster. Los dulces y los villanos son para la noche.'
  },
  {
    nivel: 'alto',
    dia: 'general',
    titulo: 'Radiator Springs Racers y Rise of the Resistance NO entran en tu Lightning Lane',
    detalle: 'Las dos atracciones más demandadas del resort están fuera del Multi Pass: son Lightning Lane Single Pass, que se compra aparte y por atracción. Radiator Springs Racers en California Adventure y Star Wars: Rise of the Resistance en Disneyland. Justo las dos que uno supondría cubiertas.',
    accion: 'Racers se resuelve con rope drop: entra a Cars Land sin detenerte y la haces en los primeros 20 minutos. Rise no se puede rope-dropear bien, así que ahí sí conviene pagar el Single Pass un solo día, el sábado. La excepción es si lo que tienen es Premier Pass, que sí las incluye.'
  },
  {
    nivel: 'medio',
    dia: 'sab-12',
    titulo: 'Sábado es el día más lleno de la semana en Disneyland',
    detalle: 'Tu reservación de Fantasmic ancla el sábado en Disneyland y no se puede mover. Sábado con Halloween Time es el pico de la semana.',
    accion: 'Con Multi Pass el sábado deja de dar miedo, pero el rope drop sigue siendo obligatorio: las primeras dos horas valen más que cuatro Lightning Lanes.'
  },
  {
    nivel: 'medio',
    dia: 'mar-8',
    titulo: 'El 8 es el único día de Disney sin Lightning Lane',
    detalle: 'Ese día entran con boleto de Oogie Boogie Bash, que es admisión al evento y no boleto de parque, así que no hay Multi Pass. Encima, durante las horas de la fiesta el servicio queda suspendido para todos. De 15:00 a 18:00 el parque sigue en operación normal y las filas todavía están en niveles de día.',
    accion: 'Tu sustituto es la fila de Single Rider de Radiator Springs Racers: te separan al subir pero es la misma atracción, y corta la espera a la mitad o menos. Es la única fila larga que te vas a encontrar el día 8.'
  },
  {
    nivel: 'medio',
    dia: 'mar-8',
    titulo: 'El check-in del hotel es a las 15:00 y tú entras al parque a esa hora',
    detalle: 'No vas a poder entrar a la habitación antes del parque. Llegar con maletas al carro y dejarlas a la vista mientras andas de compras es la receta clásica de un cristalazo.',
    accion: 'Pasa al hotel a las 14:00, deja el equipaje en bell services (es gratis aunque no tengas cuarto listo), cámbiate al disfraz ahí y sal ligero al parque.'
  },
  {
    nivel: 'medio',
    dia: 'general',
    titulo: 'California va una hora atrás que CDMX',
    detalle: 'CDMX es UTC-6 todo el año. Tijuana, San Diego y Los Ángeles están en horario de verano del Pacífico (UTC-7) en septiembre. Tu celular cambia solo al aterrizar.',
    accion: 'Todas las horas de esta app ya están en hora de California. Tu vuelo sale 5:32 hora CDMX y aterriza 7:32 hora Tijuana: son ~3 horas de vuelo, no 2.'
  },
  {
    nivel: 'medio',
    dia: 'lun-14',
    titulo: 'Falta la hora del vuelo de regreso del 14',
    detalle: 'El día de San Diego se planea hacia atrás desde tu vuelo. Hay que devolver el Turo, cruzar el CBX y estar en la sala 2 horas antes.',
    accion: 'Regla: sal de donde estés en San Diego 4 horas antes del despegue. El cruce del CBX de regreso es más rápido (no hay migración mexicana pesada), pero la devolución del Turo y el tráfico de la I-5 sur sí muerden.'
  }
];

/* ---------- TRASLADOS ---------- */
const TRASLADOS = [
  { de: 'Aeropuerto de Tijuana (TIJ)', a: 'Lado americano del CBX (Otay Mesa)', km: '0.4 km a pie', tiempo: '30–45 min', nota: 'Incluye caminar el puente y migración de EE.UU. En hora pico puede pasar de 1 hora.' },
  { de: 'CBX / Otay Mesa', a: 'Anaheim', km: '~185 km', tiempo: '1h55–2h25', nota: 'Aquí recoges el Turo. CA-905 y luego I-5 norte. Ojo con Camp Pendleton y con la zona de Irvine.' },
  { de: 'Hotel', a: 'Disneyland (Uber, ida)', km: '~5 km', tiempo: '10 min + 10 de caminata', nota: 'Al punto oficial de Harbor Blvd. En la mañana no hay surge ni fila.' },
  { de: 'Disneyland', a: 'Hotel (Uber, regreso)', km: '~5 km', tiempo: '12 min de caminata + espera + 10 de viaje', nota: 'Pídelo desde el McDonald\'s de Harbor Blvd, nunca desde la zona oficial al cierre.' },
  { de: 'Anaheim', a: 'Buena Park (compras)', km: '13 km', tiempo: '15–20 min', nota: 'Clúster de Target, Ross y Marshalls sobre la I-5.' },
  { de: 'Anaheim', a: 'Dodger Stadium', km: '74 km', tiempo: '1h15–2h', nota: 'Salir antes de las 16:30 o el tráfico de la I-5 / SR-110 te come el primer inning.' },
  { de: 'Anaheim', a: 'Universal Studios Hollywood', km: '64 km', tiempo: '1h–1h45', nota: 'Peor entre 7:00 y 9:30. Salir 6:30 para llegar a la apertura.' },
  { de: 'Anaheim', a: 'Santa Monica Pier', km: '77 km', tiempo: '1h10–1h50', nota: 'Estacionamiento del muelle es caro; el Lot 4 North Beach sale mejor.' },
  { de: 'Anaheim', a: 'San Diego (centro)', km: '150 km', tiempo: '1h40–2h15', nota: 'De regreso el día 14.' },
  { de: 'San Diego (centro)', a: 'CBX / Otay Mesa', km: '30 km', tiempo: '25–35 min', nota: 'Devolver el Turo antes. Presupuesta 40 min extra por si el host pide entrega en otro punto.' }
];

/* ---------- ITINERARIO DÍA POR DÍA (horas de California) ---------- */
const DIAS = [
{
  id: 'mar-8', fecha: '2026-09-08', dow: 'Martes', num: 1,
  titulo: 'Llegada y Oogie Boogie Bash',
  subtitulo: 'CDMX → TIJ → CBX → San Diego → Anaheim → DCA',
  badge: 'Día bisagra', parque: 'dca-obb',
  resumen: 'El día más frágil del viaje: cinco eslabones seguidos (vuelo, cruce, renta, manejo, compras) antes de una hora fija que no perdona. Todo lo que se atrase antes de la 13:40 se paga con tiempo de fiesta.',
  bloques: [
    { t:'03:15', kind:'auto', titulo:'Salida de casa al AICM', texto:'Hora CDMX. Con vuelo a las 5:32 quieres estar documentando a las 3:45.', why:'Volaris y compañía cierran documentación 45 min antes. Perder este vuelo tira el día 1 completo, incluido el Oogie Boogie.' },
    { t:'05:32', kind:'vuelo', titulo:'Despegue CDMX → Tijuana', texto:'Vuelo de ~3 horas. Duerme: hoy te acuestas a la 1 de la mañana.' },
    { t:'07:32', kind:'vuelo', titulo:'Aterrizaje en Tijuana (TIJ)', texto:'Ya en hora del Pacífico. Tu celular cambia solo.', why:'Aquí empieza el reloj real del día. Cualquier retraso del vuelo se lo come la ventana de compras, no la fiesta.' },
    { t:'07:40', t2:'08:15', kind:'cruce', titulo:'Equipaje documentado', texto:'Si documentaste maletas, esta es la parte más lenta e impredecible del día en TIJ.', why:'Viajar sólo con equipaje de mano te ahorra entre 20 y 40 minutos justo aquí. Si puedes, viaja ligero: total, hoy vas al Target.' },
    { t:'08:15', t2:'09:00', kind:'cruce', titulo:'Cruce por el CBX', texto:'Boleto de $20–27 USD por persona, cómpralo EN LÍNEA desde ahora. Necesitas pase de abordar de un vuelo TIJ dentro de 24 h y tu visa o documento válido para EE.UU.', why:'El puente en sí son 5 minutos; lo que toma tiempo es migración estadounidense. 30–45 min es lo normal, pero presupuesta hasta 1 hora.', alerta:true },
    { t:'09:00', t2:'09:35', kind:'auto', titulo:'Recoger el Turo AQUÍ MISMO, en el CBX', texto:'Sin escalas ni Uber a San Diego. Video de 360° del auto antes de arrancar, revisa nivel de gasolina, prueba el aire acondicionado y confirma cómo se pagan las casetas.', why:'Recogerlo en el CBX en vez del aeropuerto de San Diego te ahorra 40 minutos de traslado y de trámite. Ese tiempo se va entero a la ventana de compras, que pasa de 85 minutos a poco más de dos horas.', alerta:true },
    { t:'09:35', t2:'11:35', kind:'auto', titulo:'CBX → Buena Park por la I-5', texto:'~185 km desde Otay Mesa, entre 1h55 y 2h25. Buen momento para desayunar algo rápido en el camino.', why:'Otay Mesa está más al sur que el aeropuerto, así que el manejo es 30 km más largo. Aun así sales ganando 40 minutos netos.' },
    { t:'11:35', t2:'13:40', kind:'compras', titulo:'COMPRAS — Target, Ross y Marshalls', texto:'Clúster de Buena Park, sobre la I-5 y a 15 min de Disneyland. Ahora tienes 2 horas en vez de 85 minutos. Orden sugerido: Ross primero (lo más tardado de revisar), luego Marshalls, y Target al final porque ahí encuentras todo rápido.', why:'Ross y Marshalls requieren escarbar; Target es de pasillo directo. Si el reloj se aprieta, Target es el que puedes hacer en 20 minutos.', alerta:true },
    { t:'13:40', kind:'nota', titulo:'⏰ HORA LÍMITE — salir de compras', texto:'Aunque quede fila en la caja. Este es el único candado del día.', why:'A partir de aquí todo es tiempo mínimo: 20 min al hotel, 25 min de cambio y traslado, 15 min de seguridad. No hay colchón.', alerta:true },
    { t:'14:00', t2:'14:25', kind:'hotel', titulo:'Hotel: dejar maletas y cambiarse', texto:'Deja el equipaje en bell services aunque el cuarto no esté listo (es gratis). Cámbiate al disfraz aquí, no en el estacionamiento del parque.', why:'Dejar maletas y bolsas de compras a la vista en el carro durante 8 horas en un estacionamiento de Disney es el error más caro que puedes cometer hoy. Y a 10 minutos del parque, pasar al hotel casi no te cuesta tiempo.' },
    { t:'14:25', t2:'14:45', kind:'auto', titulo:'Uber al parque, deja el carro en el hotel', texto:'Pide el Uber al punto oficial de Harbor Blvd: te deja a un paso de la explanada, más cerca que cualquier estacionamiento.', why:'Te ahorras los $40 del estacionamiento y, sobre todo, los 20 minutos de tram y caminata desde la estructura. Con entrada fija a las 15:00, eso vale más que el dinero.' },
    { t:'14:45', kind:'parque', titulo:'Seguridad y torniquetes de DCA', texto:'Fórmate 15 min antes de las 15:00. Reglas de disfraz: nada de máscaras que cubran toda la cara en adultos, ni armas de utilería realistas.', why:'A las 15:00 en punto abren el acceso para boletos de la fiesta. Estar en los primeros 200 significa llegar a Radiator Springs Racers con el parque todavía en modo día.' },
    { t:'15:00', t2:'18:00', kind:'atraccion', titulo:'VENTANA DE ORO: atracciones grandes', texto:'El parque se está vaciando porque a las 18:00 sacan a todos los que no traen boleto de fiesta. Hoy no hay Lightning Lane: usa Single Rider en Racers e Incredicoaster. Plan completo en la pestaña Parques.', why:'Es la única ventana del viaje donde una atracción de 75 minutos de fila baja a 25 sin pagar nada. Empieza a las 15:00 en niveles de día y para las 17:30 ya está en caída libre.' },
    { t:'18:00', t2:'23:00', kind:'show', titulo:'OOGIE BOOGIE BASH', texto:'Dulces, villanos, Villains Grove, desfile Frightfully Fun y Mickey\'s Trick and Treat. Plan hora por hora en la pestaña Parques.' },
    { t:'23:00', t2:'23:40', kind:'hotel', titulo:'Salida: Uber desde el McDonald\'s', texto:'No pidas el Uber en la zona oficial. Camina a Harbor Blvd, cruza al McDonald\'s y pídelo desde ahí. Luego, check-in real y recoger el equipaje de bell services.', why:'Llevas 21 horas despierto. La tentación de "una atracción más" a las 23:00 se paga el miércoles a las 6:45.' }
  ]
},
{
  id: 'mie-9', fecha: '2026-09-09', dow: 'Miércoles', num: 2,
  titulo: 'Disneyland (medio día) + Dodgers',
  subtitulo: 'Rope drop 8:00 · Dodgers vs Rojos de Cincinnati 19:10',
  badge: 'Día partido', parque: 'dl-medio',
  resumen: 'Dos actividades grandes con un traslado de LA en medio. Funciona sólo si el rope drop es real y la salida a las 15:45 es innegociable.',
  bloques: [
    { t:'06:45', kind:'hotel', titulo:'Salida del hotel', texto:'Desayuna algo en el cuarto. No pierdas 30 min en un restaurante.' },
    { t:'07:00', kind:'nota', titulo:'📱 Reservar la 1ª Lightning Lane del día', texto:'Las reservas abren a las 7:00 en punto en la app. No necesitas estar en el parque: hazlo desde el cuarto, mientras desayunan. Sugerencia de hoy: Indiana Jones con regreso lo más temprano posible.', why:'La primera reserva es la única con horarios buenos disponibles, y arranca el reloj de 2 horas para la siguiente. Reservarla a las 7:00 en vez de a las 8:30 te regala una atracción extra en el día.', alerta:true },
    { t:'07:05', t2:'07:30', kind:'auto', titulo:'Uber al parque, punto de Harbor Blvd', texto:'Deja el carro en el hotel: lo vas a necesitar en la tarde para el Dodger Stadium. Objetivo: estar en los torniquetes a las 7:30.', why:'Hoy es el único día donde manejar saldría unos 20 minutos más rápido, porque a las 15:30 saldrías directo del estacionamiento al estadio. Con Uber tienes que pasar al hotel por el carro. Si un día quieres hacer la excepción, es éste.' },
    { t:'07:35', kind:'nota', titulo:'Escanear boleto y reservar la 1ª Lightning Lane', texto:'En cuanto pasas el torniquete ya puedes reservar. Aprovecha los 25 min de espera de la cuerda.', why:'La primera reserva del día es la más valiosa: es la única con inventario de horarios buenos.' },
    { t:'08:00', t2:'15:45', kind:'parque', titulo:'DISNEYLAND — plan de medio día', texto:'Ruta completa en la pestaña Parques. Prioridad: Fantasyland al rope drop, Haunted Mansion Holiday e Indiana Jones antes de mediodía.' },
    { t:'15:30', kind:'nota', titulo:'⏰ HORA LÍMITE — salir del parque', texto:'Sin "una última atracción". Camina a Harbor Blvd y pide el Uber desde el McDonald\'s.', why:'Se adelantó 15 minutos respecto al plan con carro: caminar al McDonald\'s, esperar el Uber y pasar al hotel por el carro son unos 40 minutos. Salir a las 15:30 protege tu llegada al estadio.', alerta:true },
    { t:'16:10', t2:'18:00', kind:'auto', titulo:'Hotel → Dodger Stadium, ya en tu carro', texto:'74 km. Con tráfico de las 16:30 son 1h15 en un buen día y 2h en uno malo. El estacionamiento del estadio abre 2.5 h antes del juego.', why:'Salir 30 minutos más tarde no te cuesta 30 minutos: te cuesta 50, porque entras de lleno al pico de la I-5 y la SR-110.', alerta:true },
    { t:'18:00', t2:'19:10', kind:'deporte', titulo:'Llegada, estacionamiento y entrada', texto:'Compra el pase de estacionamiento EN LÍNEA por adelantado, sale más barato que en la puerta. Las puertas abren ~1.5 h antes.', why:'Llegar 1 hora antes te deja ver práctica de bateo y comprar el Dodger Dog sin fila de 40 minutos en el 3er inning.' },
    { t:'19:10', kind:'deporte', titulo:'⚾ Dodgers vs Cincinnati Reds', texto:'Primer lanzamiento. Juego de ~3 horas.' },
    { t:'22:15', t2:'23:30', kind:'auto', titulo:'Regreso al hotel', texto:'Salir del estacionamiento del Dodger Stadium toma 30–45 min si te esperas al último out.', why:'Truco de local: sal en la parte baja del 8º inning o quédate 20 minutos después del final. Salir justo al terminar es lo peor de los dos mundos.' }
  ]
},
{
  id: 'jue-10', fecha: '2026-09-10', dow: 'Jueves', num: 3,
  titulo: 'Universal Studios Hollywood',
  subtitulo: 'Posible noche de Halloween Horror Nights',
  badge: 'Verificar horario', parque: 'universal',
  resumen: 'Universal es un parque de un solo día bien hecho. Si el 10 es noche de HHN, el parque diurno cierra temprano y hay que exprimir la mañana.',
  bloques: [
    { t:'06:30', kind:'auto', titulo:'Salida de Anaheim', texto:'64 km a Universal City. Entre 1h y 1h45 según el tráfico de la mañana.', why:'Salir a las 7:00 en lugar de 6:30 puede costarte 40 minutos reales: es plena hora pico hacia LA.' },
    { t:'08:00', kind:'parque', titulo:'Llegada y estacionamiento', texto:'Estacionamiento General o Preferred. De ahí caminas por CityWalk a la entrada.', why:'Del carro a los torniquetes hay 10–15 min de caminata que casi nadie contabiliza.' },
    { t:'08:30', kind:'nota', titulo:'Fila en torniquetes + revisar cola virtual', texto:'Al entrar, revisa de inmediato si Super Nintendo World está con cola virtual en la app. Si lo está, tómala en ese segundo.', why:'La cola virtual de Super Nintendo World se agota en la primera hora en días llenos. Es lo único del parque que se puede acabar.', alerta:true },
    { t:'09:00', t2:'17:00', kind:'parque', titulo:'UNIVERSAL — plan de ataque', texto:'Ruta completa en la pestaña Parques. Regla de oro: baja al Lower Lot primero, todos se quedan arriba.' },
    { t:'17:00', kind:'nota', titulo:'⚠️ Posible cierre por HHN', texto:'Si es noche de Halloween Horror Nights, desalojan a quien no traiga boleto del evento. Confirma en la app de Universal.', why:'HHN 2026 corre del 3 de septiembre al 1 de noviembre en noches selectas y arranca a las 19:00.', alerta:true },
    { t:'17:30', t2:'19:00', kind:'ocio', titulo:'CityWalk: cena y compras', texto:'Está fuera del parque, no necesita boleto y es la mejor opción de cena cerca.', why:'Si el parque cierra temprano, CityWalk salva la noche sin manejar hasta LA con hambre.' },
    { t:'19:00', t2:'20:30', kind:'auto', titulo:'Regreso a Anaheim', texto:'El tráfico de salida de LA ya bajó a esta hora.' }
  ]
},
{
  id: 'vie-11', fecha: '2026-09-11', dow: 'Viernes', num: 4,
  titulo: 'Disney California Adventure',
  subtitulo: 'Día completo · World of Color en la noche',
  badge: 'Día completo', parque: 'dca',
  resumen: 'El día más relajado de los cuatro de Disney. DCA se hace completo en un día si empiezas por Cars Land.',
  bloques: [
    { t:'06:50', kind:'hotel', titulo:'Uber al parque', texto:'A esta hora no hay surge y el viaje son 10 minutos. Reserva tu primera Lightning Lane a las 7:00 desde el camino: va en Web Slingers o Guardians, NO en Racers.', why:'Racers no está en el Multi Pass, ésa se gana con rope drop, y para eso hay que estar en la puerta a las 7:30.' },
    { t:'07:30', kind:'parque', titulo:'En los torniquetes de DCA', texto:'Objetivo: estar entre los primeros para Radiator Springs Racers.' },
    { t:'08:00', t2:'21:00', kind:'parque', titulo:'DCA — plan de ataque', texto:'Ruta completa en la pestaña Parques. Racers al rope drop, Avengers Campus a media mañana, Pixar Pier en la tarde.' },
    { t:'21:00', kind:'show', titulo:'🌊 World of Color', texto:'Agarra lugar 45 min antes en Paradise Gardens Park, del lado izquierdo viendo la laguna. Confirma horario exacto en la app.', why:'Es el show que NO pudiste ver el día 8 porque el parque cerró a las 18:00 por la fiesta. Hoy es tu única oportunidad.' },
    { t:'21:30', kind:'nota', titulo:'Salida sin prisa: Uber desde el McDonald\'s', texto:'Con Uber no hay último corrido que perder. Camina a Harbor Blvd, cruza al McDonald\'s y pide desde ahí.', why:'Y como no tienes hora límite, esperar 15 o 20 minutos juega a tu favor: el surge del cierre baja rápido en cuanto se vacía la primera oleada.' }
  ]
},
{
  id: 'sab-12', fecha: '2026-09-12', dow: 'Sábado', num: 5,
  titulo: 'Disneyland + Fantasmic',
  subtitulo: 'Reservación River Belle Terrace · 2º show de Fantasmic',
  badge: 'Día pico', parque: 'dl-completo',
  resumen: 'Sábado con Halloween Time es el día más lleno de tu semana. También es el mejor: fuegos artificiales y Fantasmic la misma noche, en el orden correcto.',
  bloques: [
    { t:'06:45', kind:'hotel', titulo:'Uber al parque', texto:'Diez minutos y sin surge a esta hora. Hoy el rope drop importa más que ningún otro día.', why:'Desde enero de 2026 nadie entra antes que nadie: se acabó la entrada anticipada de los hoteles Disney. El que llegue primero a la explanada gana, y en sábado ése puedes ser tú.' },
    { t:'07:00', kind:'nota', titulo:'📱 Reservar la 1ª Lightning Lane del día', texto:'Desde el cuarto, a las 7:00 en punto. Hoy la mejor primera reserva es Haunted Mansion Holiday: es la que más se dispara en sábado.', why:'En sábado los horarios de regreso se agotan de verdad. Media hora de retraso hoy te cuesta las ventanas de la mañana.', alerta:true },
    { t:'07:30', kind:'parque', titulo:'En los torniquetes de Disneyland', texto:'Objetivo real: cruzar antes de las 7:45.' },
    { t:'08:00', t2:'18:00', kind:'parque', titulo:'DISNEYLAND — plan de día completo', texto:'Ruta en la pestaña Parques. Haunted Mansion Holiday y Space Mountain con overlay de Halloween son las prioridades del día.' },
    { t:'18:00', kind:'nota', titulo:'Siesta en el hotel — ahora sí hazla', texto:'A 10 minutos y en Uber, ir y volver te cuesta una hora y te devuelve la noche completa. Regresa al parque a las 19:00 para tu reservación.', why:'Vas a estar de pie hasta las 23:30 y llevas cinco días de parque encima. Estando tan cerca, saltarte la siesta es desperdiciar la ventaja principal de tu hotel.' },
    { t:'19:15', kind:'comida', titulo:'🍽️ River Belle Terrace — paquete Fantasmic', texto:'Confirma tu hora exacta de comida al reservar: el paquete estándar sienta desde las 16:00 y el premium a las 19:15. Estándar ~$64 adulto / $36 niño; premium ~$94 / $49, sin impuestos ni propina.', why:'El paquete incluye pase a un área reservada en Rivers of America. No necesitas apartar lugar 2 horas antes como todos los demás: ese es todo el valor de lo que pagaste.', alerta:true },
    { t:'21:10', kind:'nota', titulo:'Posicionarse en el hub para los fuegos', texto:'Ve al Central Plaza (la rotonda frente al castillo) y párate del LADO OESTE, es decir el que ve hacia Frontierland.', why:'Es la respuesta a tu pregunta: desde el hub ves las proyecciones completas del castillo Y quedas a 6 minutos caminando del área reservada de Fantasmic. Desde Main Street ves igual de bien pero después tienes que caminar contra toda la multitud.', alerta:true },
    { t:'21:30', kind:'show', titulo:'🎆 Halloween Screams (fuegos artificiales)', texto:'~13 minutos. Confirma horario del día en la app; en septiembre suele ser a las 21:30.' },
    { t:'21:50', t2:'22:05', kind:'nota', titulo:'Caminar a Rivers of America', texto:'Sal en cuanto termine el último trueno, sin esperar a que apaguen las luces. Entra al área reservada del paquete.', why:'25 minutos de colchón antes del show. Suficiente sin ser una eternidad de pie.' },
    { t:'22:30', kind:'show', titulo:'🐉 Fantasmic — 2º show', texto:'~25 minutos, desde tu área reservada. Confirma horario en la app.', why:'El 2º show es el correcto para ti: te deja ver los fuegos de las 21:30 completos antes. Con el 1er show habrías tenido que elegir.' },
    { t:'23:00', kind:'nota', titulo:'Salida: caminar al McDonald\'s de Harbor Blvd', texto:'No pidas el Uber en la zona oficial de Harbor: al cierre la fila de choferes se desborda sobre la avenida y tu carro no puede entrar. Camina a Harbor, cruza al McDonald\'s de enfrente y pide desde ahí.', why:'Es la salida más lenta de tu semana, con 40 mil personas saliendo a la vez por la misma puerta. El McDonald\'s te saca del cuello de botella y te da dónde sentarte mientras llega.', alerta:true },
    { t:'23:30', kind:'nota', titulo:'Deja que baje el surge', texto:'Como no tienes hora límite, no pasa nada si esperas. Compara Uber y Lyft antes de confirmar: al cierre casi nunca cuestan lo mismo.', why:'El pico de tarifa dura lo que tarda en salir la primera oleada. Veinte minutos de café pueden costar la mitad que pedirlo a las 23:02.' }
  ]
},
{
  id: 'dom-13', fecha: '2026-09-13', dow: 'Domingo', num: 6,
  titulo: 'Universal (2ª vuelta) y Los Ángeles',
  subtitulo: 'Día flexible',
  badge: 'Flexible', parque: 'la',
  resumen: 'Si ya exprimiste Universal el jueves, este día rinde mucho más como día de Los Ángeles. Aquí están las dos versiones.',
  bloques: [
    { t:'07:30', kind:'auto', titulo:'Salida de Anaheim', texto:'Domingo en la mañana el tráfico a LA es notablemente mejor que entre semana.' },
    { t:'09:00', t2:'13:00', kind:'ocio', titulo:'OPCIÓN A — Universal 2ª vuelta', texto:'Sólo tiene sentido si el jueves te quedaste con ganas de Super Nintendo World o si el parque cerró temprano por HHN. Ojo: el 13 también puede ser noche de HHN.', why:'Universal se agota en un día bien hecho. Un segundo día completo casi siempre se siente repetido.' },
    { t:'09:00', t2:'11:00', kind:'ocio', titulo:'OPCIÓN B — Griffith Observatory', texto:'Entrada gratis. Llega antes de las 10:00 porque el estacionamiento se satura. La vista del letrero de Hollywood desde aquí es la buena.', why:'Es lo mejor de LA que no cuesta nada y a las 9:00 de un domingo todavía está vacío.' },
    { t:'11:30', t2:'13:30', kind:'ocio', titulo:'OPCIÓN B — Hollywood Blvd y Paseo de la Fama', texto:'Teatro Chino, huellas en el cemento, Dolby Theatre. Hora y media alcanza de sobra.', why:'Es una calle que se disfruta 90 minutos y se sufre 4 horas. Vete con hambre de más.' },
    { t:'14:30', t2:'19:00', kind:'ocio', titulo:'Santa Monica Pier y Venice Beach', texto:'Estaciona en el Lot 4 North Beach y camina. La rueda de la fortuna del muelle al atardecer es la foto del viaje.', why:'El atardecer en septiembre en Santa Monica es alrededor de las 19:10. Llegar a las 14:30 te da tarde de playa y te deja el atardecer.' },
    { t:'19:30', t2:'21:00', kind:'auto', titulo:'Regreso a Anaheim', texto:'Domingo en la noche fluye bien.' }
  ]
},
{
  id: 'lun-14', fecha: '2026-09-14', dow: 'Lunes', num: 7,
  titulo: 'San Diego y regreso',
  subtitulo: 'Devolver Turo · CBX · vuelo a CDMX',
  badge: 'Falta hora de vuelo', parque: 'sd',
  resumen: 'Este día se planea AL REVÉS, desde tu hora de vuelo. Llena el dato en cuanto lo tengas y recorta actividades desde el final.',
  bloques: [
    { t:'07:30', kind:'hotel', titulo:'Check-out de Anaheim', texto:'Sal con todo el equipaje en la cajuela, no en el asiento trasero.', why:'Vas a estacionarte en zonas turísticas de San Diego todo el día con las maletas dentro. Cajuela cerrada, sin nada a la vista.' },
    { t:'09:30', kind:'ocio', titulo:'La Jolla Cove', texto:'Lobos marinos a metro y medio de distancia, gratis. Estaciónate en Coast Blvd.', why:'Es lo más memorable de San Diego por hora invertida y está sobre la ruta de regreso.' },
    { t:'11:30', kind:'comida', titulo:'Comida en Little Italy o Old Town', texto:'Old Town si quieres el San Diego histórico; Little Italy si quieres comer bien.' },
    { t:'13:30', kind:'ocio', titulo:'Balboa Park o Coronado', texto:'Balboa Park: jardines y museos, se camina. Coronado: la playa y el Hotel del Coronado, se maneja por el puente.', why:'Elige uno. Los dos el mismo día con hora de vuelo encima es como se pierden los vuelos.' },
    { t:'—', kind:'nota', titulo:'⏰ REGLA DE ORO DEL REGRESO', texto:'Sal de donde estés en San Diego CUATRO HORAS antes de tu despegue: 40 min de traslado + 40 min de devolución del Turo + 30 min al CBX + 45 min de cruce + 2 h de anticipación en sala. Ajusta hacia arriba, nunca hacia abajo.', why:'Es el único tramo del viaje sin plan B. Si pierdes el vuelo en TIJ, el siguiente puede ser al día siguiente.', alerta:true },
    { t:'—', kind:'cruce', titulo:'Devolución del Turo y cruce del CBX', texto:'Llena el tanque antes de devolver (el host cobra premium por gasolina). Fotos de entrega. Boleto del CBX de regreso comprado desde ahora.', why:'El cruce de regreso hacia México es más rápido que el de entrada, pero la devolución del Turo es el paso que se atrasa.' }
  ]
}
];

/* ---------- PLANES DE ATAQUE POR PARQUE ---------- */
const PARQUES = {
'dca-obb': {
  nombre: 'Oogie Boogie Bash — California Adventure',
  fecha: 'Martes 8 · 15:00 a 23:00',
  horario: 'Entrada con boleto de fiesta desde 15:00 · Fiesta 18:00–23:00 · El parque cierra al público general a las 18:00',
  ll: 'Hoy NO tienes Lightning Lane: tu boleto es de evento, no de parque. Y aunque lo tuvieras, durante la fiesta queda suspendido. No hace falta: de 18:00 en adelante las filas son cortas solas. Lo único que sí duele es Racers entre 15:00 y 17:00, y eso se resuelve con Single Rider.',
  principios: [
    'De 15:00 a 18:00 el parque se está VACIANDO. Es tu mejor ventana de atracciones grandes de todo el viaje, y es gratis.',
    'De 18:00 a 20:00 todos corren a lo mismo: dulces y villanos. Las filas de caramelos llegan a 40 minutos.',
    'De 21:30 a 23:00 los senderos de dulces se quedan vacíos, siguen surtidos, y las atracciones quedan casi sin fila.',
    'Lo único verdaderamente escaso son los encuentros con villanos. Elige TRES y olvídate del resto.',
    'Sin Lightning Lane hoy, tu herramienta es la fila de Single Rider: Radiator Springs Racers e Incredicoaster la tienen. Te separan al subir, nada más.'
  ],
  ruta: [
    { t:'15:00', a:'Radiator Springs Racers — por Single Rider', n:'Directo a Cars Land al entrar, sin escalas. Mira el tiempo publicado y decide: si Single Rider está abierta, ésa; si la espera normal marca 40 min o menos, standby; si marca 60+ y no hay Single Rider, déjala y regresa a las 17:30, cuando el parque ya se está vaciando.', tag:'clave' },
    { t:'15:50', a:'Web Slingers: A Spider-Man Adventure', n:'Avengers Campus, a un lado de Cars Land. Ruta natural.' },
    { t:'16:25', a:'Guardians of the Galaxy – Mission: BREAKOUT!', n:'Sigue en Avengers Campus.' },
    { t:'17:00', a:'Incredicoaster', n:'Cruzas a Pixar Pier. Aquí ya se nota el parque vaciándose.' },
    { t:'17:30', a:'Racers (si la dejaste) o Toy Story / Soarin\'', n:'Si a las 15:00 Racers marcaba 60+, ésta es tu segunda oportunidad: el parque ya se está vaciando. Si ya la hiciste, Toy Story Midway Mania o Soarin\', el que tenga menos fila.' },
    { t:'17:50', a:'📍 Posicionarte para las 18:00', n:'Camina hacia donde estará tu villano prioritario #1. Revisa ubicaciones en el mapa de la app de Disneyland ese mismo día.', tag:'clave' },
    { t:'18:00', a:'Villano prioritario #1', n:'Los que revientan más rápido: Oogie Boogie, Dr. Facilier, Hades y Cruella. A las 18:05 su fila es de 20 min; a las 19:00 es de 70.', tag:'clave' },
    { t:'18:40', a:'2 senderos de dulces de camino', n:'No te desvíes: sólo los que queden sobre tu ruta al siguiente villano.' },
    { t:'19:20', a:'Mickey\'s Trick and Treat', n:'Show en el Palace Theatre. Llega 20 min antes. Confirma horarios en la app del día.' },
    { t:'20:00', a:'Villains Grove', n:'En Redwood Creek. Recorrido de niebla, luz y sonido, capacidad limitada. Es de lo mejor de la noche y muy poca gente lo pone en su lista.', tag:'joya' },
    { t:'20:40', a:'Atracciones de noche', n:'Guardians e Incredicoaster de noche son otra experiencia. Filas mínimas.' },
    { t:'21:30', a:'Frightfully Fun Parade — SEGUNDO desfile', n:'Hay dos pases. El segundo tiene bastante menos gente. Buen lugar: Hollywood Land o Buena Vista Street.', tag:'clave' },
    { t:'22:00', a:'🍬 BARRIDA DE DULCES', n:'Última hora: recorre todos los senderos que te faltan. Siguen surtidos y ahora son de caminar sin parar. Aquí es donde se llena la bolsa de verdad.', tag:'clave' },
    { t:'23:00', a:'Salida', n:'Pasa por Buena Vista Street de salida si quieres comprar algo.' }
  ],
  evitar: [
    'Formarte a un sendero de dulces entre las 18:00 y las 20:00. Es la hora de fila más larga de toda la noche para lo que después es de caminar.',
    'Ver el PRIMER desfile. Úsalo como ventana de atracciones vacías.',
    'Intentar hacer todos los encuentros de villanos. No cabe: son 3 en una noche realista.',
    'Cenar en el parque entre 18:00 y 19:30. Come algo sustancioso ANTES de las 17:00 o durante el primer desfile.'
  ],
  oro: [
    'Lleva una bolsa de tela plegable extra en la mochila. Las bolsitas que dan se llenan rápido.',
    'Si alguien tiene alergias, en la entrada dan una bolsa color teal: la cambias al final por dulces sin alérgenos.',
    'Disfrázate en el hotel. Adultos: sin máscaras que cubran toda la cara, sin armas de utilería realistas, sin capas que arrastren.',
    'Las fotos con villanos son la mejor compra de PhotoPass del viaje: los fotógrafos les meten efectos temáticos. Ojo: hoy el PhotoPass NO viene incluido, porque va con el Multi Pass y hoy no lo tienes.',
    'Confirma en la app si la fila de Single Rider sigue abierta al llegar: a veces la cierran por la tarde.'
  ]
},

'dl-medio': {
  nombre: 'Disneyland — plan de medio día',
  fecha: 'Miércoles 9 · 8:00 a 15:45',
  horario: 'Parque 8:00–22:00 · Tú sales a las 15:45 por el juego de los Dodgers',
  ll: 'Ya lo tienes: primera reserva a las 7:00 desde el cuarto. Con medio día la regla es redimir rápido, no acumular: cada vez que escaneas, se desbloquea la siguiente de inmediato. Rise of the Resistance NO está incluida (es Single Pass aparte).',
  principios: [
    'Haz rope drop en Fantasyland, no en Galaxy\'s Edge. Las atracciones de Fantasyland son cortas, están juntas y tienen las peores filas del día si las dejas para después.',
    'NO hagas rope drop de Rise of the Resistance: la caminata es larga, la atracción se descompone seguido, dura mucho y medio parque va corriendo para allá. Va con Single Pass o no va.',
    'La siguiente Lightning Lane se desbloquea cuando escaneas la actual O a las 2 horas de haberla reservado, lo que pase primero. Con medio día, escanear temprano es lo que multiplica tus reservas: no dejes correr el reloj de 2 horas.',
    'Reserva siempre el horario de regreso MÁS TEMPRANO disponible. Hoy no hay noche que aprovechar: sales a las 15:45.',
    'Come antes de las 12:00 o después de las 14:00. Nunca en medio.'
  ],
  ruta: [
    { t:'07:00', a:'📱 1ª Lightning Lane, desde el hotel', n:'Indiana Jones con el regreso más temprano que te dé. A las 9:00 la escaneas y desbloqueas la siguiente al instante.', tag:'clave' },
    { t:'08:00', a:'Peter Pan\'s Flight', n:'La primera del día, siempre. Es la peor relación fila/capacidad del parque: a las 10:00 son 60 minutos por una atracción de 3.', tag:'clave' },
    { t:'08:20', a:'Alice in Wonderland' },
    { t:'08:35', a:'Mr. Toad\'s Wild Ride o Casey Jr.', n:'Lo que esté más vacío. Fantasyland en la primera hora se hace casi corriendo.' },
    { t:'08:50', a:'Matterhorn Bobsleds', n:'Justo al salir de Fantasyland.' },
    { t:'09:15', a:'Indiana Jones Adventure', n:'Con tu Lightning Lane. Al escanear, reserva de inmediato la siguiente: Haunted Mansion Holiday.', tag:'clave' },
    { t:'09:50', a:'Pirates of the Caribbean', n:'Alta capacidad, casi nunca pasa de 30 min en la mañana.' },
    { t:'10:20', a:'Haunted Mansion Holiday', n:'Con Lightning Lane. Overlay completo de El Extraño Mundo de Jack, de lo más buscado de Halloween Time: en la tarde son 75+ minutos. Al escanear, reserva Space Mountain.', tag:'clave' },
    { t:'11:00', a:'Big Thunder Mountain Railroad' },
    { t:'11:40', a:'🍽️ Comida temprana', n:'Bengal Barbecue, Harbour Galley o Rancho del Zocalo. Comer a las 11:40 te ahorra 25 min de fila.' },
    { t:'12:30', a:'Star Wars: Galaxy\'s Edge', n:'Millennium Falcon sí entra en tu Multi Pass. Rise of the Resistance no: ésa es Single Pass aparte, $15–35 por persona. En medio día yo me la saltaría y la dejaría para el sábado.' },
    { t:'13:30', a:'Space Mountain', n:'Con tu Lightning Lane. En Halloween Time suele traer overlay temático: confirma en la app.' },
    { t:'14:15', a:'Relleno rápido', n:'Jungle Cruise, Buzz Lightyear, Star Tours o Roger Rabbit, según filas.' },
    { t:'15:15', a:'Main Street: compras y foto del castillo', n:'Main Street está abierta y no hay que caminar de más.' },
    { t:'15:45', a:'⏰ SALIDA — sin excepciones', n:'Al carro. Los Dodgers no esperan.', tag:'clave' }
  ],
  evitar: [
    'Llegar "a la hora de apertura". Llegar a las 8:00 al estacionamiento es llegar al parque a las 8:40.',
    'Rope drop de Galaxy\'s Edge. Es la trampa clásica.',
    'Comprar comida en Main Street a mediodía.'
  ],
  oro: [
    'Mobile Order en la app de Disneyland: pides desde la fila de otra atracción y sólo pasas a recoger.',
    'Single Rider en Matterhorn e Indiana Jones si no les importa separarse: corta la espera a la mitad.',
    'Llena botellas de agua gratis en las fuentes; en el parque el agua embotellada cuesta $5.'
  ]
},

'universal': {
  nombre: 'Universal Studios Hollywood',
  fecha: 'Jueves 10 · desde la apertura',
  horario: 'Confirma apertura en la app (9:00 típico en septiembre) · En noches de Halloween Horror Nights el parque diurno cierra temprano',
  ll: 'Ojo: tu Lightning Lane es de Disney y aquí no sirve de nada. El equivalente de Universal es Express Pass, se compra aparte y puede duplicar el costo del boleto. Con rope drop bien hecho un jueves de septiembre no lo necesitas.',
  principios: [
    'El parque está en dos niveles unidos por escaleras eléctricas larguísimas. Al abrir, TODOS se quedan en el Upper Lot. Bájate al Lower Lot de inmediato: es la ventaja gratis más grande de este parque.',
    'El Studio Tour hay que hacerlo antes de las 11:00. Después se va a 60–90 minutos y no baja en todo el día.',
    'Super Nintendo World puede operar con cola virtual. Si la tiene, tómala en el segundo en que cruzas los torniquetes.',
    'Universal se termina en un día bien hecho. No lo estires.'
  ],
  ruta: [
    { t:'Apertura', a:'📱 Cola virtual de Super Nintendo World', n:'Revisa la app apenas entres. Si hay cola virtual, tómala antes de caminar a ningún lado.', tag:'clave' },
    { t:'+3 min', a:'Bajar al Lower Lot por las escaleras', n:'Sin detenerte arriba. Esta decisión te ahorra 2 horas de fila acumuladas.', tag:'clave' },
    { t:'Apertura +10', a:'Jurassic World – The Ride', n:'Te vas a mojar. Impermeable barato o guarda el celular.' },
    { t:'+45 min', a:'Revenge of the Mummy', n:'Está al lado.' },
    { t:'+75 min', a:'Transformers: The Ride 3D', n:'Cierra el Lower Lot completo.' },
    { t:'~10:15', a:'Subir y hacer el Studio Tour', n:'Tiene que ser antes de las 11:00. Es la atracción insignia y la única que no se repone.', tag:'clave' },
    { t:'~11:30', a:'Super Nintendo World: Mario Kart', n:'Si tienes cola virtual, respeta tu ventana. La tierra entera es muy fotogénica: reserva tiempo para verla, no sólo para la atracción.' },
    { t:'13:00', a:'🍽️ Comida', n:'Antes de las 13:00 o después de las 14:00. Toadstool Cafe en Nintendo World es el más temático.' },
    { t:'14:00', a:'Wizarding World of Harry Potter', n:'Forbidden Journey y Flight of the Hippogriff. Hogsmeade de tarde tiene mejor luz para fotos.' },
    { t:'15:00', a:'The Secret Life of Pets y The Simpsons Ride', n:'Rellenos del Upper Lot, filas moderadas.' },
    { t:'16:00', a:'Un show', n:'WaterWorld o el Special Effects Show. Sentarte 25 minutos a media tarde salva las piernas.' },
    { t:'17:00', a:'⚠️ Posible cierre por HHN', n:'Si es noche del evento, desalojan. Sal a CityWalk a cenar.', tag:'clave' }
  ],
  evitar: [
    'Empezar por el Upper Lot. Es el error que comete el 90% de la gente y el que te regala el Lower Lot vacío.',
    'Dejar el Studio Tour para después de comer.',
    'Pagar estacionamiento Preferred: la diferencia real son 5 minutos de caminata.'
  ],
  oro: [
    'Las escaleras eléctricas del Lower Lot son larguísimas: bajas rápido pero subes lento. Planea subir UNA sola vez.',
    'CityWalk está fuera del parque y no cobra entrada: es la mejor cena de la zona y no gastas horario de parque.',
    'Si el 10 resulta ser noche de HHN, el 13 es tu comodín para lo que te falte.'
  ]
},

'dca': {
  nombre: 'Disney California Adventure — día completo',
  fecha: 'Viernes 11 · 8:00 a cierre',
  horario: 'Confirma horario en la app. Viernes suele cerrar 21:00–22:00 con World of Color.',
  ll: 'Cuidado con la trampa del día: Radiator Springs Racers NO está en el Multi Pass, es Single Pass aparte. Tus reservas de hoy van en Web Slingers, Guardians, Incredicoaster, Toy Story y Soarin\'. Racers se gana con rope drop.',
  principios: [
    'Radiator Springs Racers es LA atracción de este parque y NO la cubre tu Multi Pass. O la haces en los primeros 20 minutos del día, o pagas el Single Pass aparte, o esperas 80 minutos. No hay cuarta opción.',
    'Tu primera Lightning Lane a las 7:00 va en Web Slingers, para tenerla lista cuando salgas de Cars Land.',
    'DCA es mucho más caminable que Disneyland y se hace completo en un día sin correr.',
    'Guarda Grizzly River Run para la hora de más calor y Pixar Pier para el atardecer.',
    'World of Color es lo que NO pudiste ver el día 8 porque el parque cerró a las 18:00 por la fiesta.'
  ],
  ruta: [
    { t:'08:00', a:'Radiator Springs Racers', n:'Rope drop directo a Cars Land, sin detenerte en Buena Vista Street. Es toda la partida de hoy.', tag:'clave' },
    { t:'08:45', a:'Luigi\'s Rollickin\' Roadsters y Mater\'s Junkyard Jamboree', n:'Ya estás en Cars Land y están vacías.' },
    { t:'09:15', a:'Web Slingers: A Spider-Man Adventure', n:'Con tu Lightning Lane de las 7:00. Al escanear, reserva Incredicoaster.', tag:'clave' },
    { t:'09:50', a:'Guardians of the Galaxy – Mission: BREAKOUT!' },
    { t:'10:30', a:'Incredicoaster', n:'Ya en Pixar Pier.' },
    { t:'11:00', a:'Toy Story Midway Mania' },
    { t:'11:40', a:'🍽️ Comida temprana', n:'Pacific Wharf / Lamplight Lounge. Antes de las 12:00 siempre.' },
    { t:'12:30', a:'Soarin\' Over California' },
    { t:'13:15', a:'Grizzly River Run', n:'A propósito a esta hora: es cuando más calor hace y cuando más se disfruta mojarse.', tag:'joya' },
    { t:'14:00', a:'Bloque tranquilo', n:'The Little Mermaid, Monsters Inc., Golden Zephyr, Silly Symphony Swings. Todo de baja fila.' },
    { t:'15:00', a:'Pixar Pier completo', n:'Pixar Pal-A-Round, Jessie\'s Critter Carousel, Inside Out Emotional Whirlwind.' },
    { t:'16:30', a:'Un show o entretenimiento de temporada', n:'Revisa la app del día. Halloween Time trae entretenimiento extra en Buena Vista Street.' },
    { t:'17:30', a:'🍽️ Cena', n:'Antes de posicionarte para World of Color.' },
    { t:'19:00', a:'Segunda vuelta a Radiator Springs Racers', n:'De noche, con Cars Land iluminada, es una atracción distinta. Vale la repetida.', tag:'joya' },
    { t:'20:15', a:'📍 Lugar para World of Color', n:'Paradise Gardens Park, del lado izquierdo viendo la laguna. 45 minutos antes.', tag:'clave' },
    { t:'21:00', a:'🌊 World of Color', n:'Confirma el horario exacto en la app: cambia según el día.' }
  ],
  evitar: [
    'Entrar y detenerte a tomar fotos en Buena Vista Street al abrir. Esos 10 minutos son 40 de fila en Racers.',
    'Dejar Racers para la tarde sin Lightning Lane.',
    'Cenar después de las 18:30 si quieres buen lugar para World of Color.'
  ],
  oro: [
    'Single Rider en Radiator Springs Racers y en Incredicoaster: espera muchísimo menor si aceptan separarse.',
    'Cars Land al anochecer, cuando se encienden los neones de la Ruta 66, es la mejor foto de los dos parques.',
    'Si compras Lightning Lane un solo día de los cuatro, que sea el sábado, no hoy.'
  ]
},

'dl-completo': {
  nombre: 'Disneyland — día completo + noche de shows',
  fecha: 'Sábado 12 · 8:00 a 23:00',
  horario: 'Parque 8:00–23:00 · Halloween Screams ~21:30 · Fantasmic 2º show ~22:30 (confirmar en la app)',
  ll: 'Hoy es el día que más rinde tu Multi Pass: sábado en Halloween Time. Primera reserva a las 7:00 en Haunted Mansion Holiday. Y es el único día donde vale la pena pagar el Single Pass de Rise of the Resistance aparte, porque tienes el día completo para amortizarlo.',
  principios: [
    'Sábado es el día más lleno. Tener Multi Pass no sustituye el rope drop: las dos primeras horas del día valen más que cuatro Lightning Lanes.',
    'Todas tus Lightning Lanes se usan entre 8:00 y 18:00. De 19:15 en adelante es cena y shows, ahí ya no vas a subirte a nada.',
    'Tu noche ya está resuelta y en el orden correcto: fuegos a las 21:30, Fantasmic a las 22:30. Ese es exactamente el motivo por el que el 2º show es el que había que reservar.',
    'El paquete de comida te da área reservada. No tienes que apartar lugar 2 horas antes: ese es todo el valor de lo que pagaste.',
    'Después de Fantasmic hay una salida masiva. No te formes en ella.'
  ],
  ruta: [
    { t:'07:00', a:'📱 1ª Lightning Lane: Haunted Mansion Holiday', n:'Desde el cuarto. En sábado es la que más rápido se queda sin ventanas de regreso.', tag:'clave' },
    { t:'08:00', a:'Peter Pan\'s Flight', n:'Otra vez la primera. Un sábado a las 11:00 son 80 minutos.', tag:'clave' },
    { t:'08:20', a:'Alice in Wonderland' },
    { t:'08:35', a:'Matterhorn Bobsleds' },
    { t:'09:00', a:'Indiana Jones Adventure', n:'Fila normal a esta hora todavía es razonable.' },
    { t:'09:40', a:'Haunted Mansion Holiday', n:'Con tu Lightning Lane de las 7:00. Prioridad absoluta de Halloween Time: en sábado por la tarde pasa de 90 minutos. Al escanear, reserva Space Mountain.', tag:'clave' },
    { t:'10:20', a:'Pirates of the Caribbean' },
    { t:'10:50', a:'Big Thunder Mountain Railroad' },
    { t:'11:30', a:'Jungle Cruise' },
    { t:'12:00', a:'🍽️ Comida temprana', n:'Antes de las 12:15 o vas a perder 40 minutos formado.' },
    { t:'13:00', a:'Star Wars: Galaxy\'s Edge', n:'Millennium Falcon entra en tu Multi Pass. Rise of the Resistance es Single Pass aparte: si la van a pagar un día, que sea hoy. Cómprala en la mañana, los horarios de regreso se agotan.', tag:'clave' },
    { t:'14:30', a:'Space Mountain', n:'Con Lightning Lane. Confirma en la app si trae overlay de temporada.' },
    { t:'15:15', a:'Tomorrowland', n:'Star Tours, Buzz Lightyear, Astro Orbitor.' },
    { t:'16:00', a:'Fantasyland pendiente', n:'it\'s a small world, Storybook Land, Snow White, Pinocchio. Baja intensidad a propósito: vas a necesitar piernas en la noche.' },
    { t:'17:00', a:'New Orleans Square y compras', n:'También revisa si está Madame Leota\'s Street Party u otro entretenimiento de temporada en la app.' },
    { t:'18:00', a:'😴 Descanso', n:'Al hotel si aguantas el traslado, o siéntate a cenar temprano. La noche apenas empieza.', tag:'clave' },
    { t:'19:15', a:'🍽️ River Belle Terrace — paquete Fantasmic', n:'Confirma tu hora exacta al reservar. Guarda el pase del área reservada que te dan al terminar.', tag:'clave' },
    { t:'21:10', a:'📍 Central Plaza, lado oeste', n:'La rotonda frente al castillo, parado del lado que ve hacia Frontierland. Ves las proyecciones completas Y quedas a 6 minutos del área de Fantasmic.', tag:'clave' },
    { t:'21:30', a:'🎆 Halloween Screams', n:'~13 minutos de fuegos con proyecciones sobre el castillo, Main Street y la Matterhorn.' },
    { t:'21:50', a:'Caminar a Rivers of America', n:'Sal apenas termine, sin esperar. Entra al área reservada con tu pase.' },
    { t:'22:30', a:'🐉 Fantasmic — 2º show', n:'~25 minutos desde tu área reservada.', tag:'clave' },
    { t:'23:00', a:'NO salgas todavía', n:'Métete a una atracción de Frontierland o compra algo en Main Street. Sal a las 23:30 y te ahorras 35 minutos de fila del tram.', tag:'clave' }
  ],
  evitar: [
    'Ver Halloween Screams desde Main Street. Se ve igual de bien pero después caminas contra 30 mil personas justo cuando tienes prisa.',
    'Llegar al área reservada de Fantasmic a las 22:25. Llega 22:05 y siéntate cómodo.',
    'Salir del parque entre 23:00 y 23:15.'
  ],
  oro: [
    'Confirma los horarios exactos de Fantasmic y Halloween Screams en la app de Disneyland el mismo día: cambian y a veces se cancelan por viento.',
    'Si el paquete premium de River Belle está disponible, el upgrade son ~$25 por persona llamando al (714) 781-DINE. Vista al río incluida.',
    'Lleva una sudadera. En septiembre Anaheim baja a 17°C de noche y tú vas a estar sentado al aire libre desde las 22:00.'
  ]
}
};

/* ---------- LISTAS DE VERIFICACIÓN ---------- */
const CHECKLISTS = [
  { id:'antes', titulo:'Antes de salir', icon:'📋', items:[
    'Pasaportes vigentes y visas de EE.UU. de todos',
    'Boletos del CBX comprados en línea (ida y vuelta)',
    'Turo confirmado CON ENTREGA EN EL CBX: punto exacto, costo de entrega y cómo se reciben las llaves',
    'Avisado al host de Turo el número de vuelo, por si aterrizan tarde',
    'Licencia de conducir vigente del conductor registrado en Turo',
    'Boletos de Oogie Boogie Bash descargados en la app de Disneyland',
    'Boletos de Disneyland/DCA vinculados a la app',
    'Reservación de River Belle Terrace confirmada (hora exacta de comida)',
    'Boletos de Dodgers y pase de estacionamiento comprados',
    'Boletos de Universal comprados y verificado si el 10 es noche de HHN',
    'Hotel confirmado con política de guardar equipaje antes del check-in',
    'Dirección del hotel guardada en Uber y Lyft como destino favorito',
    'Tarjeta de crédito avisada al banco de viaje a EE.UU.',
    'Seguro médico de viaje',
    'App de Disneyland descargada y con sesión iniciada ANTES de volar',
    'Plan de datos internacional o eSIM activada'
  ]},
  { id:'maleta', titulo:'Maleta', icon:'🧳', items:[
    'Disfraces de Oogie Boogie Bash (sin máscara facial completa en adultos)',
    'Tenis muy cómodos, ya usados. Dos pares si es posible',
    'Sudadera o chamarra ligera: las noches en Anaheim bajan a 17°C',
    'Bloqueador solar',
    'Gorra o sombrero',
    'Impermeable barato o bolsas ziploc para Grizzly River Run y Jurassic World',
    'Baterías portátiles (una por persona, la app de Disney devora batería)',
    'Cables de carga',
    'Bolsa de tela plegable para los dulces de Oogie Boogie',
    'Termos o botellas rellenables',
    'Medicamentos personales y botiquín básico',
    'Maleta vacía o extra plegable para las compras'
  ]},
  { id:'dia8', titulo:'Día 8 — el día crítico', icon:'⚡', items:[
    'Pases de abordar guardados: los pide el CBX',
    'Alarma puesta a la 13:40 (hora límite de compras)',
    'Efectivo en dólares para propinas y estacionamientos',
    'Disfraces en una bolsa aparte y accesible, no al fondo de la maleta',
    'Confirmado con el host de Turo el punto exacto de entrega en el CBX',
    'Uber y Lyft instaladas, con tarjeta cargada y probadas antes de viajar',
    'Video de 360° del auto al recibirlo',
    'Ubicación del hotel guardada sin conexión en el mapa'
  ]},
  { id:'parque', titulo:'Mochila diaria de parque', icon:'🎒', items:[
    'Batería portátil cargada',
    'Botella de agua rellenable',
    'Bloqueador y bálsamo labial',
    'Snacks (sí se permiten alimentos en Disneyland)',
    'Sudadera para la noche',
    'Efectivo pequeño',
    'Curitas o bandas para ampollas'
  ]}
];

/* ---------- CÓMO LLEGAR, DÍA POR DÍA ---------- */
const TRANSPORTE = {
  dias: [
    { d:'Mar 8',  m:'Uber',  c:'~$15', p:'Del hotel al parque. El carro se queda estacionado: hoy ya trabajó de sobra.' },
    { d:'Mié 9',  m:'Uber',  c:'~$30', p:'Ida y vuelta al hotel, y de ahí en tu carro al Dodger Stadium. Sal del parque a las 15:30.' },
    { d:'Jue 10', m:'Carro', c:'—',    p:'Universal Studios Hollywood, a 64 km. No hay alternativa.' },
    { d:'Vie 11', m:'Uber',  c:'~$35', p:'Ida y vuelta. El regreso, después de World of Color, con surge.' },
    { d:'Sáb 12', m:'Uber',  c:'~$55', p:'Cuatro viajes: parque, siesta, regreso y salida final. El de las 23:00 es el caro.' },
    { d:'Dom 13', m:'Carro', c:'—',    p:'Los Ángeles y Santa Monica.' },
    { d:'Lun 14', m:'Carro', c:'—',    p:'San Diego y regreso por el CBX.' }
  ],
  ahorro: 'Unos $135 USD de Uber contra $160 de estacionamiento en los mismos cuatro días. Sale parecido, pero es puerta a puerta: sin tram, sin caminata desde la estructura y sin manejar de noche después de dieciséis horas de pie.',
  mcdonalds: {
    titulo: 'El truco del McDonald\'s',
    porque: 'El punto oficial de Uber y Lyft sobre Harbor Blvd es chico para el tamaño del parque. Al cierre, la fila de choferes esperando entrar se desborda sobre la avenida: tú esperas y tu carro no llega. Y es justo el momento de mayor tarifa del día.',
    como: [
      'Sal del parque por la explanada principal hacia Harbor Blvd.',
      'Cruza la avenida por el paso peatonal. El McDonald\'s queda enfrente.',
      'Pide el viaje desde ahí, con el pin puesto en el McDonald\'s y no en "Disneyland".',
      'Escribe al chofer en qué esquina estás: a esa hora hay mucha gente esperando.',
      'Compara Uber y Lyft antes de confirmar. Al cierre casi nunca cuestan lo mismo.'
    ],
    ojo: [
      'De la puerta del parque al McDonald\'s son 10 a 15 minutos caminando. Cuéntalos.',
      'Sólo para el REGRESO. Para llegar en la mañana usa el punto oficial: no hay fila y queda más cerca.',
      'Crucen juntos Harbor Blvd, sobre todo de noche y con niños cansados.'
    ]
  }
};

/* ---------- LIGHTNING LANE: mecánica ---------- */
const LIGHTNING_LANE = {
  fuera: [
    'Star Wars: Rise of the Resistance — Disneyland',
    'Radiator Springs Racers — California Adventure'
  ],
  reglas: [
    { t:'Una reserva activa a la vez',
      d:'En Disneyland el Multi Pass no es como el de Florida. Tienes una selección a la vez y la siguiente se desbloquea cuando escaneas la actual O cuando pasan 2 horas desde que la reservaste, lo que ocurra primero.' },
    { t:'Escanear temprano rinde más que esperar',
      d:'Si redimes a la hora, la siguiente se desbloquea de inmediato. Redimiendo cada hora sacas bastante más reservas al día que dejando correr el reloj de 2 horas. En un día completo la diferencia son 3 o 4 atracciones.' },
    { t:'La primera se reserva a las 7:00, desde donde estés',
      d:'No necesitas estar dentro del parque ni haber pasado el torniquete. Hazla desde la cama. Es la única reserva del día con horarios de regreso realmente buenos.' },
    { t:'Cambiar de atracción no reinicia el reloj',
      d:'Si reservas una y luego la modificas por otra del mismo parque, el contador de 2 horas sigue corriendo desde la reserva original. Sirve para corregir sin castigo.' },
    { t:'Funciona en los dos parques',
      d:'El Multi Pass cubre Disneyland y California Adventure. Para caminar de un parque al otro el mismo día sí necesitas boleto Park Hopper, que es otra cosa.' },
    { t:'PhotoPass incluido',
      d:'Todas las fotos con fotógrafo de Disney vienen incluidas. No compren PhotoPass aparte y abusen de los fotógrafos, sobre todo en los encuentros de villanos del Oogie Boogie.' },
    { t:'El día 8 no aplica',
      d:'Ese día entran con boleto de Oogie Boogie Bash, que es admisión al evento y no al parque, así que no hay Multi Pass. Además el servicio queda suspendido durante las horas de la fiesta. Da igual: las filas del evento son cortas y Racers se resuelve con Single Rider.' }
  ],
  orden: [
    'Mié 9 · Disneyland medio día: Indiana Jones → Haunted Mansion Holiday → Space Mountain → Millennium Falcon',
    'Vie 11 · California Adventure: Web Slingers → Incredicoaster → Toy Story Midway Mania → Soarin\' → Guardians',
    'Sáb 12 · Disneyland completo: Haunted Mansion Holiday → Space Mountain → Indiana Jones → Millennium Falcon → Matterhorn → Big Thunder'
  ]
};

/* ---------- PRESUPUESTO: categorías sugeridas ---------- */
const CATEGORIAS_GASTO = ['Comida','Parques','Transporte','Compras','Hotel','Souvenirs','Otro'];

/* ---------- FUENTES CONSULTADAS ---------- */
const FUENTES = [
  { t:'Oogie Boogie Bash — información oficial', u:'https://disneyland.disney.go.com/events-tours/disney-california-adventure/oogie-boogie-bash-halloween-party/' },
  { t:'Oogie Boogie Bash 2026: fechas y detalles (Disney Parks Blog)', u:'https://disneyparksblog.com/dlr/oogie-boogie-bash-everything-you-need-to-know/' },
  { t:'Oogie Boogie Bash 2026 — fechas y precios (Disney Tourist Blog)', u:'https://www.disneytouristblog.com/2026-oogie-boogie-bash-halloween-party-dates-details/' },
  { t:'Estrategia de rope drop en Disneyland (Disney Tourist Blog)', u:'https://www.disneytouristblog.com/morning-plan-disneyland-rope-drop-strategy/' },
  { t:'Estrategia matutina en Disneyland (Mickey Visit)', u:'https://mickeyvisit.com/morning-strategy-disneyland/' },
  { t:'Horarios de Disneyland, septiembre 2026 (Rope Drop News)', u:'https://ropedropnews.com/parks/disneyland/hours/2026-09' },
  { t:'Paquetes de comida de Fantasmic (Disneyland oficial)', u:'https://disneyland.disney.go.com/dining/disneyland/fantasmic-dinner-packages/' },
  { t:'River Belle Terrace — menú y precios del paquete (AllEars)', u:'https://allears.net/dlr/dining/menu/river-belle-terrace/special-dinner/' },
  { t:'Halloween Screams — información oficial', u:'https://disneyland.disney.go.com/entertainment/disneyland/halloween-screams/' },
  { t:'Guía de Lightning Lane en Disneyland 2026', u:'https://www.enchantedinsider.com/disneyland-lightning-lane-complete-guide-2026/' },
  { t:'Lightning Lane Passes — Disneyland oficial', u:'https://disneyland.disney.go.com/lightning-lane-passes/' },
  { t:'Cambios a las reglas de Lightning Lane en Disneyland 2026 (AllEars)', u:'https://allears.net/2025/12/16/disneyland-lightning-lane-rules-are-changing-in-2026/' },
  { t:'Multi Pass y Single Pass: qué cubre cada uno (WDW Prep School)', u:'https://wdwprepschool.com/lightning-lane-passes/' },
  { t:'Halloween Horror Nights 2026 Hollywood — fechas', u:'https://blog.discoveruniversal.com/events/halloween-horror-nights-2026-universal-studios-hollywood-lineup/' },
  { t:'Cross Border Xpress — sitio oficial', u:'https://www.crossborderxpress.com/' },
  { t:'Calendario de los Dodgers 2026 (MLB)', u:'https://www.mlb.com/dodgers/schedule/2026/fullseason' },
  { t:'Uber y Lyft en Disneyland: puntos de ascenso y descenso (Mickey Visit)', u:'https://mickeyvisit.com/disneyland-uber-lyft-dropoff-pickup-tips/' },
  { t:'Guía del punto de Harbor Boulevard 2026 (Enchanted Insider)', u:'https://www.enchantedinsider.com/how-to-harbor-boulevard-guest-drop-off-pick-up-for-disneyland/' },
  { t:'Turo en Cross Border Xpress — ayuda oficial', u:'https://help.turo.com/en_us/cross-border-xpress-(cbx)-or-hosts-S1dzwQZfyl' },
  { t:'Fin de la entrada anticipada en los hoteles Disneyland (Disney Tourist Blog)', u:'https://www.disneytouristblog.com/free-lightning-lane-for-on-site-hotel-guests-at-disneyland-resort-early-entry-ending-in-2026/' },
  { t:'Precios de estacionamiento en Disneyland 2026', u:'https://www.enchantedinsider.com/disneyland-parking/' }
];
