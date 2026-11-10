export const meta = {
  name: 'ligamx-modelos',
  description: 'Cerebro Liga MX: arnes walk-forward sin fugas, variables a la fecha, competencia de familias de modelos, seleccion con periodo de prueba y auditoria de fugas',
  phases: [
    { title: 'Cimientos', detail: 'arnes de validacion y variables a la fecha' },
    { title: 'Familias', detail: 'Dixon-Coles, ratings dinamicos y modelos con variables' },
    { title: 'Seleccion', detail: 'ensamble, prueba unica y campeon' },
    { title: 'Auditoria', detail: 'caza de fugas y replica independiente' },
  ],
}

const R = {
  type: 'object',
  properties: {
    resumen: { type: 'string' },
    archivos: { type: 'array', items: { type: 'string' } },
    hallazgos: { type: 'array', items: { type: 'string' } },
    pendientes: { type: 'array', items: { type: 'string' } },
  },
  required: ['resumen', 'archivos', 'hallazgos', 'pendientes'],
}
const saltar = (args && args.saltar) || []

const CTX = `
CONTEXTO COMUN (leelo completo)
- Proyecto "Cerebro Liga MX" en /home/user/SA/ligamx/ (repo git /home/user/SA). Hoy es 2026-11-10. El usuario es actuario: el rigor estadistico importa mas que la vistosidad; quiere "el mejor modelo posible" para pronosticar partidos de la Liga MX (resultado, marcador y mercados derivados), simular la liguilla y estimar la probabilidad de campeon, con TODAS las variables que aporten (rachas, casa/visita, dominios entre equipos, forma, ausencias, peso de cada estadio, altitud, descanso, viaje...). El sistema quedara automatizado y se reevaluara despues de cada partido y cada jornada (ciclo campeon/retador), asi que todo debe poder recalcularse rapido y sin intervencion.
- DATOS (ya construidos y conciliados): /home/user/SA/ligamx/datos/partidos.csv (8,767 partidos de Liga MX 2001-2026 desde ESPN; 8,684 jugados; una fila por partido; incluye los 10 PROGRAMADOS del Apertura 2026), goles.csv (minuto de cada gol), tarjetas.csv, alineaciones.csv (titulares y cambios), calendario_pendiente.json, tabla_apertura2026.csv. LEE /home/user/SA/ligamx/datos/COBERTURA.md: trae el diccionario de columnas y la cobertura por torneo. Resumen: marcador a 90 min (gl, gv), tiempos extra y penales aparte (gl_et, gv_et, pen_l, pen_v), medio tiempo (gl_ht, gv_ht) desde 2001; fase (regular | repechaje | cuartos | semifinal | final) y pierna (1 ida, 2 vuelta); estadisticas por lado (tiros, tiros_puerta, corners, faltas, amarillas, rojas, posesion...) con cobertura >= 80% desde Clausura 2020 y buena desde 2017 salvo Apertura 2016; alineaciones desde Clausura 2017; momios 1X2 de cierre (ml_l, ml_e, ml_v, decimales) y de apertura (ml_*_abre), mas linea de goles (total_linea, over, under), con cobertura >= 95% desde 2021; arbitro desde 2022. Los campos faltantes vienen VACIOS (no cero).
- REGLAS del torneo: /home/user/SA/ligamx/config/torneo.json (8 clasifican directo, sin play-in; en cuartos y semifinales el empate global favorece al mejor sembrado; final con tiempos extra y penales).
- MODELO PREVIO: /home/user/SA/ligamx/notas/mapa_repo_previo.md explica como llamar al motor original (Dixon-Coles con capas manuales) como linea base y sus defectos conocidos (subestima goles ~14%, ruidoso con xi=0.0038).
- ENTORNO: Python 3.13 con numpy, pandas, scipy, scikit-learn, lightgbm y xgboost. La maquina tiene 4 CPU y otro agente corre a la vez: usa como maximo 2 procesos. Ningun comando debe bloquear mas de 9 minutos: lo largo va en segundo plano (nohup, log a archivo) y lo revisas.
- CARPETA de modelado: /home/user/SA/ligamx/modelo/ (cada agente escribe SOLO en los archivos que se le asignan; lee lo demas). Predicciones y caches pesados en /home/user/SA/ligamx/modelo/pred/ y /home/user/SA/ligamx/modelo/cache/ (cache/ no va a git).
- PROTOCOLO DE VALIDACION (obligatorio para todos):
  * Walk-forward: cada partido se pronostica solo con informacion anterior a su bloque. Bloque = partidos entre dos cortes consecutivos; los cortes son cada lunes 00:00 y cada viernes 00:00 hora de la Ciudad de Mexico (asi una jornada de fin de semana es un bloque y una de media semana es otro). Existe tambien la granularidad "dia" (corte al inicio de cada dia con partidos) para el modelo final.
  * Calentamiento: 2001 a Clausura 2016. DESARROLLO: Apertura 2016 a Clausura 2025 (todo se explora aqui). PRUEBA: Apertura 2025, Clausura 2026 y Apertura 2026 (lo jugado). NADIE mira la PRUEBA salvo el agente de seleccion, una sola vez, con candidatos declarados de antemano.
  * Metrica principal: log-loss de 1X2 (logaritmo natural, sobre el resultado a 90 min). Secundarias: RPS (orden local > empate > visita), Brier multicategoria (suma sobre 3 resultados, azar 0.667), log-verosimilitud del marcador exacto (malla 0-10), acierto del pick, calibracion por deciles. Comparaciones PAREADAS por partido con error estandar por bloques (bootstrap de bloques) frente a la linea base y frente al mercado (momios sin margen) donde haya momios.
  * Cada variante probada se registra (nombre, hiperparametros, metricas de desarrollo) en un registro: elegir entre muchas variantes mirando el mismo periodo sesga a favor de la elegida y hay que poder decir cuantas se probaron.
- REGLAS: no hagas git commit ni push. NUNCA inventes datos ni resultados: si algo no mejora, se dice. Sin fugas de informacion: ninguna variable, ajuste o hiperparametro puede usar datos posteriores al corte del partido pronosticado (incluye medias globales, escalados, priors escritos conociendo el futuro, y estadisticas del propio partido). Codigo y comentarios en espanol, claro y con docstrings breves. Reproducible (semillas fijas).
`
const OUT = `Devuelve (salida estructurada): resumen (8-12 lineas con cifras), archivos (rutas absolutas creadas o modificadas), hallazgos (resultados y hechos verificados utiles para las siguientes fases, uno por elemento, con cifras), pendientes (lo que falto o es dudoso).`

// ------------------------------------------------------------- Cimientos
const pArnes = `${CTX}
TAREA: construir el ARNES DE VALIDACION y las lineas base. Archivos tuyos: /home/user/SA/ligamx/modelo/datos.py, arnes.py, metricas.py, base.py, /home/user/SA/ligamx/modelo/ARNES.md y /home/user/SA/ligamx/modelo/pruebas/test_arnes.py.
1) datos.py: cargar() devuelve los partidos con tipos correctos, fecha_utc y fecha/hora local (America/Mexico_City), ordenados; jugados() y pendientes(); bloque de cada partido (cortes lunes/viernes 00:00 local) y dia; periodo (calentamiento | desarrollo | prueba) segun el torneo. Excluye de la evaluacion (pero no del historial) los resultados de escritorio o abandonados que marca la columna nota.
2) arnes.py: interfaz minima que TODAS las familias implementaran:
     class Modelo: nombre: str; def ajustar(self, hist, corte): ...  (hist = partidos jugados con fecha_utc < corte; debe poder llamarse cientos de veces; puede guardar estado para calentar el siguiente ajuste)
                   def predecir(self, partidos): ...  -> lista de dict por partido con {"lam_l", "lam_v", "rho"} (el arnes arma la matriz de marcadores 11x11 con correccion Dixon-Coles y renormaliza) o directamente {"M": matriz 11x11 que suma 1}. Opcional {"p1x2": [pl, pe, pv]} si el modelo solo da 1X2 (entonces no entra en metricas de marcador).
   Funciones: evaluar(modelo, periodo="desarrollo", granularidad="bloque") recorre los bloques en orden, ajusta con lo anterior al corte, predice el bloque y guarda una fila por partido en modelo/pred/<nombre>.parquet (id, bloque, corte, p_l, p_e, p_v, lam_l, lam_v, logp_marcador, prob de over 2.5, de ambos anotan, y los resultados reales); comparar(nombres) -> tabla pareada; utilidades para derivar de M: 1X2, marcador mas probable, top marcadores, totales, ambos anotan. Verifica en tiempo de ejecucion que hist no contenga nada posterior al corte (assert) y registra cada evaluacion sobre PRUEBA en modelo/pred/ACCESOS_PRUEBA.log (quien, cuando, que modelo); evaluar sobre prueba exige el argumento explicito permitir_prueba=True.
   Registro de variantes: registrar(nombre, familia, hiperparametros, metricas) -> modelo/registro_variantes.jsonl.
   CLI: python3 -m modelo.arnes evaluar <modulo:Clase> [--periodo] [--granularidad]; comparar ...; resumen.
3) metricas.py: log-loss, RPS, Brier, log-verosimilitud de marcador, acierto, calibracion por deciles, y diferencias pareadas con error estandar por bootstrap de bloques (semilla fija) e intervalo de 95%.
4) base.py (lineas base, todas implementando Modelo y evaluadas en DESARROLLO): (a) Frecuencias: proporciones historicas de local/empate/visita y Poisson con medias de liga; (b) PoissonSimple: ataque y defensa por maxima verosimilitud con decaimiento exponencial (vida media 1 anio), ventaja de local comun, independiente; (c) CerebroOriginal: el motor previo llamado como indica notas/mapa_repo_previo.md en su variante limpia para backtest (sin priors ni capas escritas conociendo el futuro) y, aparte, "exacto" (solo valido para Apertura 2026 desde agosto); (d) Mercado: probabilidades implicitas de los momios de cierre y de apertura sin margen (normalizacion proporcional y metodo de Shin; compara cual calibra mejor), solo donde hay momios. El mercado es referencia, no un modelo que se pueda usar para simular rondas futuras.
5) Rendimiento: un recorrido completo de DESARROLLO (18 torneos, ~3,000 partidos, ~700 bloques) con PoissonSimple debe tardar pocos minutos; vectoriza la verosimilitud y calienta cada ajuste con el anterior.
6) pruebas/test_arnes.py (pytest): no hay fuga (un modelo espia que registra la fecha maxima de hist nunca ve el bloque), las metricas coinciden con calculos a mano en un ejemplo pequeno, la matriz suma 1, los bloques parten bien una semana con jornada doble, y evaluar es determinista.
7) ARNES.md: como implementar una familia nueva en 20 lineas, como correr, que significan las columnas, y la TABLA de lineas base en DESARROLLO (n, log-loss, RPS, Brier, logv marcador, acierto) con el mercado en el subconjunto con momios y la comparacion pareada de cada linea base contra el mercado.
${OUT}`

const pVariables = `${CTX}
TAREA: construir las VARIABLES A LA FECHA (sin fuga) para cada partido. Archivos tuyos: /home/user/SA/ligamx/modelo/variables.py, /home/user/SA/ligamx/modelo/VARIABLES.md, /home/user/SA/ligamx/modelo/pruebas/test_variables.py, /home/user/SA/ligamx/datos/estadios_sedes.csv. (Otro agente escribe en paralelo datos.py y arnes.py: no dependas de ellos; lee los CSV directamente.)
Funcion principal: construir(partidos_todos, hasta=None) -> DataFrame con una fila por partido (jugados desde 2010 y los PROGRAMADOS) y el prefijo de quien es cada variable (_l local, _v visitante, _dif diferencia). Cada valor usa SOLO partidos anteriores al inicio de ese partido (para los pendientes: todo lo jugado). Guarda modelo/cache/variables.parquet y permite actualizacion incremental rapida tras un partido nuevo.
Variables minimas (agrega las que veas utiles y documenta todas):
 a) Forma: ultimos 5 y 10 partidos (general, y solo de local / solo de visita): puntos por partido, goles a favor y en contra, diferencia; versiones con peso exponencial; forma en el torneo en curso.
 b) Rachas vigentes: victorias, sin perder, sin ganar, derrotas, anotando, sin anotar, porteria en cero (general y por condicion).
 c) Contexto de tabla antes del partido: posicion, puntos por partido, distancia en puntos al 8o lugar, partidos restantes, banderas "ya clasificado" y "ya eliminado" (matematicamente, de forma conservadora), jornada estimada.
 d) Calendario: dias de descanso de cada uno y diferencia, partidos en los ultimos 14 dias, media semana, regreso de fecha FIFA (pausa > 10 dias), hora local, mes.
 e) Sede: /home/user/SA/ligamx/datos/estadios_sedes.csv con una fila por estadio_id de ESPN (todos los que aparecen desde 2010): nombre, ciudad, lat, lon, altitud_m, superficie si se sabe, y columna fuente/confianza (parte de /home/user/SA/docs/estadios.js y de /home/user/SA/ligamx/web/medios_parts/*.json para los actuales; para los historicos usa la ciudad con valores aproximados marcados como tales). Variables: altitud de la sede, diferencia contra la altitud de la casa del visitante, distancia de viaje del visitante en km (haversine entre su sede habitual y esta), si el local juega en su sede habitual, sede compartida, ventaja de local especifica del equipo en ESE estadio (historica, encogida hacia la media de la liga con credibilidad), rendimiento historico del visitante en altura (>1,800 m) y en sintetico.
 f) Historial directo (H2H): ultimos 6 y 10 enfrentamientos (y solo en esta sede): puntos y diferencia de goles del local actual, encogidos por credibilidad; H2H solo de liguilla y solo de finales (para medir "dominios" como America sobre Cruz Azul); numero de enfrentamientos disponibles.
 g) Juego (desde que hay estadisticas; vacio si no hay): medias moviles de tiros, tiros a puerta, corners, posesion, faltas a favor y en contra; un indicador de goles esperados aproximado por tiros (regresion simple de goles sobre tiros y tiros a puerta ajustada solo con el pasado) y la diferencia goles reales menos esperados (suerte/definicion).
 h) Disciplina y ausencias derivadas de datos: rojas del equipo en su partido anterior; jugadores SUSPENDIDOS para este partido deducidos de tarjetas.csv (roja en el partido anterior; quinta amarilla acumulada en el torneo, con borron al empezar la liguilla) y su importancia (proporcion de titularidades en los ultimos 10 partidos del equipo); numero de titulares habituales ausentes.
 i) Alineacion: continuidad del once. DOS versiones claramente separadas: "_previa" (disponible al pronosticar: once del partido anterior menos suspendidos; rotacion reciente = jugadores distintos usados como titulares en los ultimos 5) y "_real" (el once que si jugo: proporcion de titulares habituales; SOLO para medir cuanto importaria saber la alineacion, marcada como no disponible al pronosticar).
 j) Fase: regular o liguilla, ronda, pierna, resultado de la ida y marcador global antes de la vuelta, diferencia de sembrado (posicion en la tabla de ese torneo), bandera "el empate global favorece al local/visitante", experiencia de liguilla (series jugadas y ganadas en los ultimos 6 torneos), finales jugadas.
 k) Mercado (marcadas "mercado_*"): probabilidades implicitas sin margen de cierre y de apertura y linea de goles. Son referencia y posible insumo, pero para rondas futuras no existen.
 l) Otros: equipo recien ascendido o con poca historia (numero de partidos previos), arbitro (media de tarjetas y de penales por partido del arbitro, solo pasado), asistencia media reciente del local.
Pruebas (pytest) de NO FUGA: para 60 partidos al azar repartidos en el tiempo, recalcula las variables usando un historial truncado justo antes del partido y exige igualdad exacta con la tabla completa; comprueba que ninguna variable no "_real" use estadisticas del propio partido; que los pendientes tengan variables; y que los vacios sean vacios (no ceros).
VARIABLES.md: tabla de todas las variables (nombre, definicion, desde cuando hay dato, disponible al pronosticar si/no) y un analisis exploratorio honesto en DESARROLLO solamente: asociacion univariada de cada grupo con el resultado mas alla de la diferencia de fuerza (por ejemplo, regresion logistica ordenada del resultado sobre una fuerza base simple + la variable; reporta coeficiente y error estandar), para orientar a quien modele: que parece tener senal (rachas, descanso, altitud, viaje, H2H, suspendidos, continuidad del once) y que no.
${OUT}`

// ------------------------------------------------------------- Familias
const famComun = `Ya existen (leelos primero): /home/user/SA/ligamx/modelo/ARNES.md, arnes.py, metricas.py, base.py, datos.py (arnes y lineas base), y /home/user/SA/ligamx/modelo/VARIABLES.md y variables.py (variables a la fecha; tabla en modelo/cache/variables.parquet). Reporte de quienes los hicieron:
ARNES = __ARNES__
VARIABLES = __VARIABLES__
Trabaja SOLO en DESARROLLO (prohibido evaluar en PRUEBA). Registra CADA variante que pruebes con arnes.registrar. Guarda las predicciones de tus mejores variantes en modelo/pred/. Al final deja declarados como maximo 3 CANDIDATOS de tu familia (clases listas para instanciar, con hiperparametros fijos) en tu modulo y descritos en tu informe, con sus metricas de desarrollo, la comparacion pareada contra PoissonSimple y contra el mercado (subconjunto con momios), cuantas variantes probaste en total, y una nota honesta de que tan robusta es la mejora (por torneo, regular vs liguilla, primeros vs ultimos anios). Si algo no mejora a la linea base, dilo. Cuida el tiempo de computo: un candidato debe poder recorrer DESARROLLO en menos de ~15 minutos y ajustarse una vez en segundos (se recalculara tras cada partido).`

const pFamDC = `${CTX}
${famComun}
TAREA: FAMILIA "poisson" (modelos de goles por maxima verosimilitud). Archivos tuyos: /home/user/SA/ligamx/modelo/familias/poisson.py y /home/user/SA/ligamx/modelo/informes/poisson.md.
Explora con criterio (no fuerza bruta ciega): Dixon-Coles con rho estimado; decaimiento temporal (vida media de 3 meses a 3 anios, y mezcla de dos escalas: forma reciente + nivel de largo plazo); regularizacion/credibilidad de ataque y defensa hacia la media (prior normal, equivale a efectos aleatorios; elegir la fuerza por validacion) para estabilizar equipos con poca historia (ascendidos: Atlante 2026); ventaja de local por equipo/estadio encogida; peso distinto a liguilla; efecto de fase (liguilla menos goles?, ida vs vuelta); binomial negativa o Poisson inflado en empates si la calibracion de empates lo pide; bivariado con covarianza; "reinicio" parcial entre torneos (los planteles cambian en cada receso). Verifica la calibracion del numero de goles y de los empates. Incluye el modelo del usuario (CerebroOriginal de base.py) como referencia en tu tabla.
${OUT}`

const pFamRatings = `${CTX}
${famComun}
TAREA: FAMILIA "ratings" (fuerzas dinamicas que se actualizan partido a partido; son la base natural de un sistema que mejora solo). Archivos tuyos: /home/user/SA/ligamx/modelo/familias/ratings.py y /home/user/SA/ligamx/modelo/informes/ratings.md.
Explora: Elo con margen de goles y ventaja de local (K, escala y regresion a la media entre torneos por validacion); pi-ratings de Constantinou (fuerza separada de local y de visita); ratings de ataque/defensa tipo Berrar o Poisson en linea (actualizacion por gradiente de la verosimilitud Poisson); filtro tipo Kalman/Glicko con incertidumbre por equipo (la incertidumbre crece en el receso y para ascendidos). Para convertir ratings en distribucion de marcadores: regresion de Poisson de goles local y visita sobre la diferencia y suma de ratings (ajustada solo con el pasado), o probit/logit ordenado para 1X2 mas un modelo de goles totales. Mide tambien que tan rapido reacciona cada rating a cambios de nivel (ejemplo: equipos con cambio de entrenador o rachas largas) frente a su ruido.
${OUT}`

const pFamVars = `${CTX}
${famComun}
TAREA: FAMILIA "variables" (modelos que usan las variables a la fecha ademas de la fuerza de los equipos). Archivos tuyos: /home/user/SA/ligamx/modelo/familias/variables_ml.py y /home/user/SA/ligamx/modelo/informes/variables.md.
Las predicciones de PoissonSimple (y de otras familias si ya estan en modelo/pred/) pueden entrar como variables de fuerza, siempre respetando el walk-forward (la prediccion de cada partido ya es fuera de muestra). Explora: (a) GLM de Poisson para goles local y visita con fuerza base + variables (regularizacion L2/L1 elegida dentro de cada ventana de entrenamiento); (b) logit multinomial u ordenado para 1X2; (c) gradient boosting (LightGBM/XGBoost) con pocas hojas y mucha regularizacion, objetivo Poisson para goles y multiclase para 1X2, con ajuste de hiperparametros ANIDADO (solo con pasado); (d) correccion multiplicativa: tomar las lambdas del mejor modelo de goles disponible y aprender un ajuste log-lineal pequeno con las variables (forma, descanso, altitud, viaje, H2H, suspendidos, continuidad del once, fase, sembrado) con fuerte encogimiento. Reentrena por torneo o por bloque segun costo. Reporta por GRUPO de variables cuanto aporta (ablacion: quitar el grupo y medir el cambio en log-loss con su error estandar): rachas, casa/visita, H2H y dominios, descanso y viaje, altitud y sede, juego por tiros, ausencias y alineacion, fase y sembrado. Version aparte "con mercado" (momios como variable) para medir cuanto agrega el modelo AL mercado y el mercado al modelo; esa version no sirve para simular rondas futuras y debe quedar marcada.
Se especialmente esceptico con mejoras pequenas: con ~3,000 partidos el error estandar del log-loss es ~0.01; una mejora menor a 2 errores estandar pareados es ruido.
${OUT}`

// ------------------------------------------------------------- Seleccion y auditoria
const pSeleccion = (fams) => `${CTX}
TAREA: SELECCION del campeon. Archivos tuyos: /home/user/SA/ligamx/modelo/ensamble.py, pronostico.py, campeon.json, registro.json, RESULTADOS.md.
Reportes de las familias: ${JSON.stringify(fams).slice(0, 9000)}
Lee los informes en /home/user/SA/ligamx/modelo/informes/ y ARNES.md.
1) ENSAMBLE (solo DESARROLLO): combina los candidatos de las familias (promedio simple; mezcla lineal y log-lineal de probabilidades con pesos aprendidos SOLO con bloques anteriores, es decir pesos walk-forward; mezcla de lambdas). Evalua si el ensamble mejora al mejor individuo mas alla del ruido y si conserva buena verosimilitud de marcador exacto (el producto final necesita una matriz de marcadores coherente, no solo 1X2).
2) PRE-REGISTRO: antes de tocar PRUEBA, escribe en RESULTADOS.md la lista cerrada de candidatos finales (maximo 6: lineas base, mejores individuales y ensambles), la metrica principal y la regla de decision: gana el de mejor log-loss 1X2 en PRUEBA; solo destrona al mejor de desarrollo si la diferencia pareada supera 2 errores estandar; ante empate estadistico se prefiere el mas simple y rapido.
3) PRUEBA (una sola vez, permitir_prueba=True, granularidad "dia"): evalua los candidatos en Apertura 2025, Clausura 2026 y Apertura 2026; tabla con n, log-loss, RPS, Brier, logv de marcador, acierto, marcadores exactos acertados, calibracion; comparacion pareada con intervalos contra PoissonSimple, contra CerebroOriginal y contra el MERCADO (cierre y apertura). Di con franqueza si se le gana o no al mercado y por cuanto.
4) campeon.json: modelo elegido, hiperparametros, metricas de desarrollo y de prueba, fecha, y por que. registro.json: campeon y RETADORES (los demas candidatos) con sus metricas, listo para un ciclo de mejora continua (tras cada jornada se reevaluan todos en walk-forward y un retador solo se adopta si mejora al campeon por mas de 2 errores estandar pareados y no empeora en los ultimos 8 bloques).
5) pronostico.py (API de produccion, la usaran el simulador de liguilla y la pagina): ajustar(corte=None) -> ajusta el campeon con todo lo jugado antes del corte; predecir(partidos) -> por partido lam_l, lam_v, rho, matriz 11x11, 1X2, y los insumos explicativos disponibles (fuerzas de cada equipo, ventaja de local, ajustes por variables con su magnitud) para poder explicar cada pronostico; fuerza_equipos() -> tabla de fuerzas actuales (ataque, defensa, rating) para simular cruces hipoteticos de liguilla entre cualesquiera dos equipos en cualquier sede; incertidumbre(n) -> n muestras de parametros (bootstrap o aproximacion normal) para propagar la incertidumbre de estimacion a la simulacion del campeon. Debe correr completo en menos de 2 minutos. Pruebalo pronosticando los 10 partidos pendientes del Apertura 2026 y pega la tabla en RESULTADOS.md.
RESULTADOS.md debe poder leerlo el usuario (actuario): que se probo (cuantas variantes), que gano, por cuanto, que tan seguro es, que NO funciono, y limites.
${OUT}`

const pAuditoria = (sel) => `${CTX}
TAREA: AUDITORIA adversarial e independiente del trabajo de modelado en /home/user/SA/ligamx/modelo/. Reporte del agente de seleccion: ${JSON.stringify(sel).slice(0, 6000)}
Tu objetivo es encontrar razones por las que los resultados reportados NO sean confiables. Por defecto desconfia.
1) FUGAS: lee arnes.py, datos.py, variables.py y el codigo del campeon y de los candidatos buscando informacion del futuro: variables calculadas con el propio partido o posteriores, escalados o medias globales, hiperparametros elegidos mirando PRUEBA, pesos de ensamble no walk-forward, "priors" con conocimiento posterior, momios de cierre usados por un modelo que dice no usar mercado, orden temporal roto por zona horaria (partidos nocturnos), partidos del mismo dia usados entre si. Para cada sospecha escribe una prueba que la confirme o la descarte.
2) REPLICA: sin usar el arnes, escribe un script independiente (modelo/pruebas/replica_independiente.py) que recalcule desde los CSV crudos el log-loss 1X2 y el RPS del campeon y de PoissonSimple en PRUEBA a partir de sus archivos de predicciones, y otro que reajuste el campeon desde cero para 30 partidos al azar de PRUEBA usando solo datos anteriores a cada uno y compare contra lo guardado. Las diferencias deben ser despreciables.
3) CONTAMINACION DE PRUEBA: revisa modelo/pred/ACCESOS_PRUEBA.log y el registro de variantes: cuantas veces se evaluo sobre PRUEBA y por quien, y si el pre-registro se respeto.
4) ESTADISTICA: verifica los errores estandar (bootstrap por bloques), que las comparaciones contra el mercado usen exactamente los mismos partidos, y que la calibracion reportada sea correcta; calcula tu mismo el numero efectivo de variantes probadas y comenta el sesgo de seleccion esperado.
5) PRODUCCION: corre pronostico.py de principio a fin, revisa que los 10 partidos pendientes tengan probabilidades sensatas (suman 1, sin NaN, coherentes con la tabla y con los momios si ya existen), y que fuerza_equipos e incertidumbre funcionen.
Corrige lo que este mal (edita el codigo, vuelve a correr lo necesario) y escribe /home/user/SA/ligamx/modelo/AUDITORIA.md: que probaste, que estaba mal y como cambio los numeros, y tu veredicto sobre que tan creible es la ventaja reportada del campeon.
${OUT}`

// ------------------------------------------------------------- Orquestacion
phase('Cimientos')
const [arnes, vars] = await parallel([
  () => saltar.includes('arnes') ? Promise.resolve({ resumen: 'ya hecho en una corrida anterior; ver ARNES.md', archivos: [], hallazgos: [], pendientes: [] }) : agent(pArnes, { label: 'arnes', phase: 'Cimientos', schema: R }),
  () => saltar.includes('variables') ? Promise.resolve({ resumen: 'ya hecho en una corrida anterior; ver VARIABLES.md', archivos: [], hallazgos: [], pendientes: [] }) : agent(pVariables, { label: 'variables', phase: 'Cimientos', schema: R }),
])
const sub = (p) => p.replace('__ARNES__', JSON.stringify(arnes).slice(0, 4000)).replace('__VARIABLES__', JSON.stringify(vars).slice(0, 4000))

phase('Familias')
const fams = await parallel([
  () => saltar.includes('poisson') ? Promise.resolve({ resumen: 'ya hecho; ver informes/poisson.md', archivos: [], hallazgos: [], pendientes: [] }) : agent(sub(pFamDC), { label: 'familia-poisson', phase: 'Familias', schema: R }),
  () => saltar.includes('ratings') ? Promise.resolve({ resumen: 'ya hecho; ver informes/ratings.md', archivos: [], hallazgos: [], pendientes: [] }) : agent(sub(pFamRatings), { label: 'familia-ratings', phase: 'Familias', schema: R }),
  () => saltar.includes('variables_ml') ? Promise.resolve({ resumen: 'ya hecho; ver informes/variables.md', archivos: [], hallazgos: [], pendientes: [] }) : agent(sub(pFamVars), { label: 'familia-variables', phase: 'Familias', schema: R }),
])

phase('Seleccion')
const sel = saltar.includes('seleccion') ? { resumen: 'ya hecho; ver RESULTADOS.md', archivos: [], hallazgos: [], pendientes: [] } : await agent(pSeleccion(fams.filter(Boolean)), { label: 'seleccion', phase: 'Seleccion', schema: R })

phase('Auditoria')
const aud = await agent(pAuditoria(sel), { label: 'auditoria', phase: 'Auditoria', schema: R })
return { arnes, vars, fams, sel, aud }
