export const meta = {
  name: 'ligamx-mercados-ensamble',
  description: 'Cerebro Liga MX: revalidar los 56 mercados y las combinadas con el modelo de produccion (ensamble), corregir sesgos con regla escrita de antemano y auditar la correccion',
  phases: [
    { title: 'Medir', detail: 'validacion walk-forward de mercados y combinadas con ensamble; diagnostico de sesgos' },
    { title: 'Corregir', detail: 'correcciones candidatas con regla escrita de antemano; integracion en produccion' },
    { title: 'Auditar', detail: 'revision independiente: fugas, sesgo de seleccion, cifras reproducidas, confirmacion unica en PRUEBA' },
  ],
}

const RAIZ = '/home/user/SA/ligamx'
const SCR = '/tmp/claude-0/-home-user-SA/2bd39326-8617-5400-b04f-4c3059628357/scratchpad/mercados'

const COMUN = `
Contexto: proyecto Cerebro Liga MX en ${RAIZ} (pronosticos de la Liga MX: 1X2, marcador, 56 mercados por partido y una «combinada» de 4 picks del mismo partido con probabilidad conjunta exacta, en tres variantes: segura, equilibrada y atrevida). Lee ${RAIZ}/produccion/MERCADOS.md (secciones 1 a 5 y 9) y, para el protocolo de validacion, ${RAIZ}/modelo/ARNES.md y ${RAIZ}/modelo/AUDITORIA.md (por partes: son largos).
Datos y protocolo: DESARROLLO = Apertura 2016 a Clausura 2025 (2,981 partidos); PRUEBA = Apertura 2025, Clausura 2026 y Apertura 2026 (480 partidos). Las predicciones walk-forward (fuera de muestra) de cada modelo estan en ${RAIZ}/modelo/pred/<modelo>.parquet (DESARROLLO) y <modelo>__prueba__dia.parquet (PRUEBA). El modelo de produccion es «ensamble» (promedio de las lambdas de «ajuste» y «elo», con rho de Dixon-Coles; ver ${RAIZ}/modelo/campeon.json). MERCADOS.md se escribio con el modelo provisional «poisson_simple»: sus tablas son de ese modelo. Comandos existentes: «python3 -m produccion.mercados validar <modelo>» y «python3 -m produccion.combinada validar <modelo>».
Reglas del proyecto que no se rompen: sin fugas (todo lo que se ajuste para pronosticar un partido usa solo partidos anteriores a su corte); PRUEBA no se usa para elegir nada (cada lectura queda anotada en modelo/pred/ACCESOS_PRUEBA.log); nada inventado: lo que no mejore mas que el ruido se dice y no se adopta; se cuenta y se informa el numero de variantes probadas. El JavaScript de la pagina no calcula probabilidades.
No hagas commit ni push ni publiques nada: de eso se encarga la sesion principal. Guiones y salidas temporales en ${SCR}/ (crea la carpeta). Presupuesto de tokens limitado: lee los archivos grandes por secciones y no vuelques tablas enormes a la conversacion.
Puede que una corrida anterior de esta misma tarea haya quedado a medias (se acaba el limite de uso): antes de empezar revisa «git -C /home/user/SA status --short» y lo que haya en ${SCR}/ y continua desde ahi.
`

const MEDICION = {
  type: 'object',
  properties: {
    resumen: { type: 'string' },
    mercados_sesgados: { type: 'array', items: { type: 'object', properties: {
      mercado: { type: 'string' }, pronosticado: { type: 'number' }, observado: { type: 'number' }, z: { type: 'number' },
      pendiente: { type: 'number' }, logloss_vs_constante: { type: 'string' } },
      required: ['mercado', 'pronosticado', 'observado', 'z'] } },
    combinadas: { type: 'array', items: { type: 'object', properties: {
      variante: { type: 'string' }, n: { type: 'number' }, prob_anunciada: { type: 'number' }, frecuencia: { type: 'number' }, z: { type: 'number' } },
      required: ['variante', 'n', 'prob_anunciada', 'frecuencia'] } },
    comparacion_con_provisional: { type: 'string' },
    diagnostico: { type: 'string', description: 'de donde sale cada sesgo (ceros de mas, rho, dispersion de las lambdas, reparto por mitades...) con cifras' },
    candidatos: { type: 'array', items: { type: 'object', properties: {
      nombre: { type: 'string' }, que_hace: { type: 'string' }, parametros_libres: { type: 'number' }, riesgo: { type: 'string' } },
      required: ['nombre', 'que_hace', 'parametros_libres'] } },
    archivos: { type: 'array', items: { type: 'string' } },
  },
  required: ['resumen', 'mercados_sesgados', 'combinadas', 'diagnostico', 'candidatos', 'archivos'],
}

const CORRECCION = {
  type: 'object',
  properties: {
    resumen: { type: 'string' },
    regla: { type: 'string', description: 'la regla de adopcion tal como quedo escrita ANTES de mirar resultados' },
    variantes_probadas: { type: 'array', items: { type: 'object', properties: {
      nombre: { type: 'string' }, resultado: { type: 'string' }, adoptada: { type: 'boolean' } }, required: ['nombre', 'resultado', 'adoptada'] } },
    adoptado: { type: 'string', description: 'que quedo en produccion (o «nada» y por que)' },
    cifras_clave: { type: 'string' },
    archivos: { type: 'array', items: { type: 'string' } },
    pruebas: { type: 'string' },
    pendientes: { type: 'array', items: { type: 'string' } },
  },
  required: ['resumen', 'regla', 'variantes_probadas', 'adoptado', 'cifras_clave', 'archivos', 'pruebas', 'pendientes'],
}

const AUDITORIA = {
  type: 'object',
  properties: {
    veredicto: { type: 'string', enum: ['se_sostiene', 'se_sostiene_con_reservas', 'no_se_sostiene'] },
    resumen: { type: 'string' },
    hallazgos: { type: 'array', items: { type: 'object', properties: {
      gravedad: { type: 'string', enum: ['alta', 'media', 'baja'] }, que: { type: 'string' }, evidencia: { type: 'string' }, que_hice: { type: 'string' } },
      required: ['gravedad', 'que', 'evidencia', 'que_hice'] } },
    confirmacion_prueba: { type: 'string', description: 'resultado de la lectura unica de PRUEBA, con cifras y errores estandar' },
    estado_final: { type: 'string', description: 'que quedo en produccion despues de la auditoria (igual, ajustado o revertido) y resultado literal de las baterias de pruebas' },
    archivos: { type: 'array', items: { type: 'string' } },
  },
  required: ['veredicto', 'resumen', 'hallazgos', 'confirmacion_prueba', 'estado_final', 'archivos'],
}

phase('Medir')
const medicion = await agent(`Eres quien MIDE como estan calibrados los mercados y las combinadas de Cerebro Liga MX con el modelo que hoy esta en produccion. ${COMUN}
Tu tarea (solo medir y diagnosticar; no cambies el codigo de produccion):
1. Corre la validacion walk-forward sobre DESARROLLO de los 56 mercados y de las tres variantes de combinada con «ensamble» (los comandos existen; si hay que adaptarlos al nombre o al rho del modelo, hazlo con un guion tuyo en ${SCR}/, sin tocar produccion). Para cada mercado: probabilidad media pronosticada contra frecuencia observada, z del sesgo, pendiente de calibracion y log-loss contra la constante (con error estandar). Para cada variante de combinada: n, probabilidad conjunta anunciada contra frecuencia con que salio completa, y por deciles si hay muestra.
2. Compara con las cifras de «poisson_simple» de MERCADOS.md: que mejoro, que empeoro, que sigue igual. En particular «ambos anotan» (antes subestimado 3.4 puntos), «anota / no anota» y los totales (antes con pendientes de 0.34 a 0.65).
3. Diagnostica de donde sale cada sesgo que pase de 2 errores estandar, con cifras: ceros pronosticados contra observados por equipo, efecto del rho de Dixon-Coles, dispersion de las lambdas (¿exageran las diferencias de goles totales entre partidos?), reparto por mitades.
4. Propon de 2 a 4 correcciones candidatas, de la mas simple a la mas ambiciosa (por ejemplo: recalibracion monotona por familia de mercado ajustada solo con el pasado; correccion de ceros o de la dependencia en la matriz conjunta; encoger el total esperado conservando el reparto local/visita), con cuantos parametros libres tiene cada una y que riesgo trae (romper la coherencia entre mercados, empeorar el 1X2, sobreajuste). No las implementes.
Escribe la medicion completa en ${RAIZ}/produccion/MERCADOS_ENSAMBLE.md (tablas comparables a las de MERCADOS.md, con fecha) y devuelve el resumen estructurado.`,
  { label: 'medicion', phase: 'Medir', schema: MEDICION })

phase('Corregir')
const correccion = await agent(`Eres quien CORRIGE (si se puede, y solo si se sostiene) los sesgos de los mercados y de las combinadas de Cerebro Liga MX. ${COMUN}
La medicion con el modelo de produccion ya esta hecha (detalle en ${RAIZ}/produccion/MERCADOS_ENSAMBLE.md). Su resumen:
${medicion ? JSON.stringify(medicion, null, 1) : '(el agente de medicion no termino: empieza por medir tu mismo con «python3 -m produccion.mercados validar ensamble» y «python3 -m produccion.combinada validar ensamble»)'}

Tu tarea:
1. ANTES de probar nada, escribe en ${RAIZ}/produccion/MERCADOS_ENSAMBLE.md la regla de adopcion: una correccion se adopta solo si, en walk-forward sobre DESARROLLO (ajustada en cada corte unicamente con partidos anteriores), mejora el log-loss de los mercados que pretende corregir en mas de 2 errores estandar pareados (por bloques), deja el sesgo de esos mercados dentro de 2 errores estandar, y no empeora en mas de 1 error estandar ni el 1X2, ni el marcador exacto, ni ninguna otra familia de mercados, ni la calibracion de las combinadas. Entre variantes que cumplan, gana la de menos parametros. Maximo 4 variantes; se informan todas, tambien las que fallen.
2. Implementa las variantes candidatas como codigo de evaluacion (guiones en ${SCR}/ o funciones nuevas, sin tocar todavia el camino de produccion), evalualas con la regla y decide. Si ninguna cumple, NO adoptes nada: documentalo y termina (es un resultado valido).
3. Si una cumple: integrala en produccion de forma que los 56 mercados y las combinadas sigan saliendo de UNA sola distribucion conjunta coherente siempre que sea posible (preferible corregir la matriz conjunta a recalibrar mercado por mercado; si recalibras por mercado, cuida que mercados complementarios sigan sumando 1 y que la probabilidad conjunta de la combinada siga siendo exacta respecto de la distribucion que se publica). El ajuste que requiera datos se hace en cada corte solo con el pasado y queda guardado donde ya se guardan los parametros de produccion. Añade pruebas en produccion/pruebas/ y actualiza MERCADOS.md (estado y seccion 9), MERCADOS_ENSAMBLE.md y salidas/CONTRATO.md si cambia algun campo. No cambies el modelo de goles (modelo/) ni las probabilidades 1X2 y de marcador que ya se sellan, salvo que la regla lo cubra y lo digas con todas sus letras.
4. Cierra con «python3 -m pytest produccion/pruebas -q» en verde y «python3 -m produccion.exportar» corriendo (tarda ~75 s: simula 1,000,000 de torneos), y comprueba en salidas/actual.json que los mercados y las combinadas de los partidos pendientes salen con la correccion.
No leas PRUEBA: la confirmacion en PRUEBA la hace despues un auditor independiente, una sola vez.`,
  { label: 'correccion', phase: 'Corregir', schema: CORRECCION })

phase('Auditar')
const auditoria = await agent(`Eres un auditor independiente y esceptico. Tu trabajo es intentar REFUTAR una correccion que otro agente acaba de hacer a los mercados y combinadas de Cerebro Liga MX, antes de que llegue a la pagina que ve el usuario. Si no se sostiene, la reviertes. ${COMUN}
Informe de la medicion previa:
${medicion ? JSON.stringify({ resumen: medicion.resumen, diagnostico: medicion.diagnostico, mercados_sesgados: medicion.mercados_sesgados, combinadas: medicion.combinadas }, null, 1) : '(sin informe)'}

Informe de quien corrigio:
${correccion ? JSON.stringify(correccion, null, 1) : '(el agente de correccion no termino: revisa «git -C /home/user/SA diff --stat» para ver que quedo a medias; si hay cambios de produccion sin validar, reviertelos con git checkout de esos archivos y dilo)'}

Que revisar (con tus propios guiones en ${SCR}/auditoria/, sin fiarte de sus cifras):
1. Fugas: ¿todo parametro de la correccion se ajusta, en cada corte, solo con partidos anteriores? Compruebalo con una prueba de truncamiento (repetir un corte quitando el futuro y ver que el resultado no cambia) o leyendo el codigo linea por linea.
2. Sesgo de seleccion: cuantas variantes se probaron de verdad (mira ${SCR}/ y el diff), si la regla se escribio antes, y cuanto de la mejora puede ser eleccion sobre ruido.
3. Reproduce de forma independiente las cifras clave (sesgo y log-loss de los mercados corregidos antes y despues, calibracion de las combinadas) sobre DESARROLLO.
4. Coherencia: mercados complementarios suman 1, ninguna probabilidad fuera de [0, 1], la probabilidad conjunta de cada combinada coincide con la de la distribucion publicada, y el 1X2 y el marcador sellados no cambiaron (o cambiaron solo como dice el informe).
5. Confirmacion en PRUEBA, UNA sola lectura (queda anotada en modelo/pred/ACCESOS_PRUEBA.log): con las predicciones ensamble__prueba__dia, ¿la correccion mejora o al menos no empeora los mercados corregidos y las combinadas? Da cifras con error estandar. PRUEBA confirma o desmiente; no se usa para reajustar nada.
Veredicto: «se_sostiene», «se_sostiene_con_reservas» (di cuales y dejalas escritas en MERCADOS_ENSAMBLE.md) o «no_se_sostiene». Si no se sostiene, o si encuentras una fuga, REVIERTE la correccion de produccion (git checkout de los archivos de produccion tocados, conservando los documentos de medicion) y deja escrito por que. Defectos menores que puedas arreglar sin cambiar el fondo: arreglalos y dilo.
Cierra con «python3 -m pytest produccion/pruebas modelo/pruebas -q» y «python3 -m produccion.exportar» y reporta su resultado literal. Añade tu auditoria a ${RAIZ}/produccion/MERCADOS_ENSAMBLE.md (seccion «Auditoria independiente»).`,
  { label: 'auditoria', phase: 'Auditar', schema: AUDITORIA })

return { medicion, correccion, auditoria }
