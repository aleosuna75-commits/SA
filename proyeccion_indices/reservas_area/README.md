# Scripts del área (RRC y SONR) con los insumos de la BD proyectada

Versiones de `reforecastRRC_v10_Esc1_ocl.py` y `ReforecastSONR_v3.py` que toman sus parámetros de la BD proyectada
(`BD_ BEL - IRR - MR_Proyeccion.xlsx`, la salida de `proyeccion_reservas.py`) en lugar de los CSV de parámetros del
área y de las constantes del año. La lógica de valuación (consultas a la base, factores de no devengamiento, cesión,
margen de riesgo, método propio del SONR, escenarios) es la de los scripts originales; cada cambio está marcado en el
código con `### INSUMOS BD`.

| Archivo | Qué es |
|---|---|
| `insumos_bd.py` | Lee la BD proyectada y arma las tablas con la forma que esperan los scripts (abajo). Se puede correr solo (con el botón Run de VS Code, sin argumentos): escribe `Parametros_usados.xlsx` en `salidas_area/` para revisar los insumos. No calcula reservas. |
| `reforecastRRC_v11_insumosBD.py` | RRC. Mismos escenarios 0 a 5 del original. |
| `ReforecastSONR_v4_insumosBD.py` | SONR. Mismos escenarios 0 a 4 del original. |
| `config_local.ejemplo.py` | Plantilla de la configuración local. Cópiala como `config_local.py` y pon tus rutas y parámetros. `config_local.py` no se versiona: lleva rutas internas y los parámetros de capital del margen de riesgo. |
| `pruebas/simulacion_sin_access.py` | Corre los dos scripts sin la base Access ni los archivos del área, con contratos y catálogos inventados, y comprueba que los índices que usan son los de la BD. Sirve para probar el código en cualquier equipo; sus montos no son reservas. |

## Scripts `_aod` del área: cambio mínimo para leer nuestros índices

`parchar_aod.py` toma `ReforecastRRC_aod.py` y `ReforecastSONR_aod.py` tal como los usa el área y escribe
`ReforecastRRC_aod_BD.py` y `ReforecastSONR_aod_BD.py` con lo mínimo cambiado (cada cambio marcado con `### INDICES BD`;
se respetan rutas, fin de línea y todo lo demás):

```
python parchar_aod.py ReforecastRRC_aod.py ReforecastSONR_aod.py
```

Regla: se parte de la tabla del área (sus renglones y columnas) y cada celda se cambia por la nuestra solo donde la BD
trae el dato; donde no lo trae se queda el valor del área. No se llenan huecos con meses vecinos.

| Insumo | Ahora |
|---|---|
| IS media y 99.5 % (RRC: `IS Bel Media-m`, `IS Bel 99.5%-m`; SONR: `Ind Sin SONR Media`, `Ind Sin SONR 99.5%`) | HParametros de la BD (`Real` hasta el último mes real, `Proyección` después). En 40, 50, 80 y 90, en RRC y en IBNR, el IS de FA (hoja `IS_FA`) en los meses proyectados. |
| `Ind. Gasto` (RRC) | `FACTOR GTO` de la BD del mes que se valúa (el área trae un solo valor por ramo). |
| `IS_Cat` (RRC, 71 y 73, por mes del contrato) | `Ind Sin RRC` de TEV e Hidro de la BD en los meses que la BD trae. |
| `LAG 1` a `LAG 10`, `Factor_Ret` (SONR) | LAG de HParametros; `Factor_Ret` = 1 − IRR / BEL del SONR de la BD. `RAMOS_FACTOR_RET_AREA` deja ramos con el del área. |
| MR | RRC: `MONTO_PI × PORC_ND × FACTOR MR × TC`; SONR: `Prima Dev × (1 − LAG) × Factor_MR`. Un 0 de la BD es dato y un MR negativo cuenta como 0, con aviso. Donde la BD no modela el ramo (sin BEL de esa reserva), la fórmula de capital del script. El MR a TC del año anterior sigue igual al de valuación, como en el script. `MR_DESDE_BD = False` vuelve a la fórmula en todo. |
| Contratos, cesión, FND calibrado, duración, retención, TC, escenario base, catálogos | Sin cambio. |

Los scripts buscan `insumos_bd.py` y la BD en `CARPETA_INDICES` (por omisión `Documents\Proyección Indices` y su
`salidas\`); la BD se reconoce por su nombre exacto, sin las variantes `_PE12`, `_PE18` ni `ProyeccionP`. Si se carga un
`insumos_bd.py` anterior (sin `VERSION_AOD` vigente) se detienen con el aviso. Los avisos de qué celdas salieron de la BD y cuáles del área
se imprimen al armar las tablas, antes del ciclo. Al final escriben `Parametros_usados_<reserva>.xlsx` junto a su
salida: las tablas que usaron, la hoja `Fuentes` (de dónde salió cada celda) y los avisos. Si la base Access no trae
tipo de cambio de un mes que se valúa, lo avisan: ese mes sale en 0 o vacío (no es la reserva), como ya pasaba.

`pruebas/simulacion_aod.py <carpeta con los _BD.py> ["<BD>"]` los corre sin Access, con tablas del área inventadas, y
compara contrato por contrato y mes por mes los índices y el MR contra los esperados.

## De dónde sale cada insumo

| Insumo del script | Antes | Ahora (`insumos_bd.py`) |
|---|---|---|
| `ParametrosMens` (RRC): `IS Bel Media-m`, `IS Bel 99.5%-m` | CSV del año | `HParametros`: `Ind Sin RRC` e `Ind sin RRC 99.5%` del mes de valuación `m`, renglones `Real` hasta el último mes real y `Proyección` después. En los ramos de `RAMOS_IS_FA` (40, 50, 80 y 90), en los meses proyectados, el IS (FA) de la hoja `IS_FA` (media y 99.5 %). |
| `Ind. Gasto` (RRC) | Un valor por ramo en el CSV | `Ind. Gasto-m`: el bloque `FACTOR GTO` (GTO / PND) del ramo y mes de valuación. El script toma el del mes que valúa (en el escenario 4, el de diciembre). |
| `Pesos_dur`, `Resto Monedas_dur`, `Pesos_ret`, `Resto Monedas_ret` (RRC, MR) | CSV del año | Siguen del CSV del área (`CSV_DURACION_RRC`): la BD no los trae. Solo se usan con `MR_DESDE = "AREA"`; en ese caso, sin el CSV el script se detiene. |
| `IS_Cat` (RRC, ramos 71 y 73 por mes del contrato) | CSV | `Ind Sin RRC` de TEV e Hidro de `HParametros` por mes (`Real` / `Proyección`). Los meses anteriores a HParametros salen del CSV del área si se indica (`CSV_IS_CAT`); si no, llevan el primer mes de HParametros, con aviso. |
| `ParamSONR`: `Ind Sin SONR Media`, `Ind Sin SONR 99.5%`, `LAG 1` a `LAG 10` | CSV del año | `HParametros` por mes de valuación y ramo (`Real` / `Proyección`); el IS (FA) de la hoja `IS_FA` en los ramos de `RAMOS_IS_FA` en los meses proyectados. |
| `Factor_Ret` (SONR) | CSV del año | `1 − IRR / BEL` de SONR de la hoja de montos, por ramo y mes. En los meses proyectados, con la `CESION` y el `FACTOR MR` proyectados (`1 − CESION × (1 + FACTOR MR / IS)`, que es lo mismo). En un mes sin BEL (el ramo 80 en la historia), el del mes más cercano con dato. Acotado a [0, 1]. |
| Tipo de cambio USD | Base Access hasta el último mes y promedio de los dos últimos meses para el resto | Base Access hasta el último mes real y, para los meses siguientes, la columna `TC` de la BD (pronóstico de Inversiones). `xTC_PPTO` (TC del escenario base) también sale de la columna `TC`. |
| Escenario 0 (año base) | CSV `Escenario_base_<reserva>` | Montos reales de diciembre del año anterior de la hoja de montos, con la convención de signos del área (RRC: BEL, BELG, IRR y MR negativos; BRUTO y NETO positivos; SONR todo positivo). |
| Escenario 1 (presupuesto) | CSV `Escenario_base_<reserva>` | Sigue del CSV si está (`ESCENARIO_BASE_CSV`); si no, no se incluye. La BD no trae saldos del presupuesto. |
| Meses del escenario 3 que el script no valúa (después del último mes real) | Renglones del presupuesto (escenario 1) | Saldos proyectados de la BD (BEL por FND y derivados), `MESES_FALTANTES_ESC3 = "BD"`. Con `"CSV"` se toman del presupuesto, como antes. |
| Año y mes de valuación | Constantes en el script (2025, 9 y 12) | El último mes real de la BD (hoy 2026 y 8). Se pueden fijar en `config_local.py` (`ANIO`, `MES`). |
| Base Access, catálogos, CSV auxiliares, presupuesto técnico, ajustes manuales | Rutas fijas en el script | Rutas en `config_local.py`. El presupuesto técnico acepta los nombres de columna de BW (`/ERP/GL_ACCT`, `0CALMONTH`). |
| Margen de riesgo (MR) | Fórmula de capital: RRC `−Desviación × RCS × COC × duración / base de capital`; SONR `Desviación / −BC × BC2`, con constantes en el script | `MR_DESDE = "BD"`: MR del contrato = su prima no devengada (RRC: `MONTO_PI × PORC_ND`; SONR: `Prima Dev × (1 − LAG)`) × el bloque `FACTOR MR` (MR / PND o PD) del ramo y mes de valuación, el mismo factor con que la BD calcula su MR. Con `MR_DESDE = "AREA"` queda la fórmula original, con sus parámetros (`RCS`, `COC`, `BC`, `BC_SONR`; `BC` y `BC2` del SONR) en `config_local.py`. |
| Contratos de la base de valuación, cesión, `PORC_ND`, `FND` | Igual | Igual. |

Los montos y factores proyectados de la hoja de montos son fórmulas: `insumos_bd.py` lee los valores que Excel guardó.
**Abre y guarda la BD en Excel antes de correr.** Si una celda no tiene valor guardado, toma el del
`Diagnostico_Proyeccion.xlsx` de la misma corrida (hojas `Indicadores_Ramo` y `Montos_Proyectados`); si tampoco, se
detiene con el mensaje de qué celda falta.

## Cómo correrlo en tu equipo

1. En una carpeta local pon: los tres `.py` (`insumos_bd.py` y los dos scripts), `config_local.py` (copia de
   `config_local.ejemplo.py` con tus rutas y parámetros) y la BD proyectada ya abierta y guardada en Excel (y, si
   quieres, su `Diagnostico_Proyeccion.xlsx`). Si la BD no está en `RUTA_BD`, los scripts toman la más reciente que
   encuentren junto a ellos o en `salidas/` (la carpeta donde la deja `proyeccion_reservas.py`) y lo avisan.
2. Revisa en `config_local.py`: la base Access, los catálogos, las carpetas de CSV auxiliares de RRC y de SONR, el
   presupuesto técnico del año y los parámetros del MR.
3. Abre `reforecastRRC_v11_insumosBD.py` o `ReforecastSONR_v4_insumosBD.py` en VS Code y dale Run (no necesitan
   argumentos ni importa en qué carpeta esté la terminal). Antes de empezar revisan todo lo que necesitan y, si algo
   falta, se detienen con la lista completa: pyodbc, el controlador de Access, la base Access, los archivos del área y
   que las salidas no estén abiertas en Excel.
4. Escriben en `salidas_area/`: `RRC_esc.xlsx`, `SONR_esc.xlsx` (la misma forma de antes) y
   `Parametros_usados_<reserva>.xlsx` con las tablas de insumos que usaron (índices por mes, `IS_Cat`, `ParamSONR`, TC,
   escenario base y saldos proyectados) y los avisos.
5. Sin Access a la mano, `pruebas/simulacion_sin_access.py` (también con Run) prueba que el código corre y toma los
   índices de la BD.

**pyodbc y el controlador de Access.** Si falta pyodbc, los scripts lo instalan con pip en el mismo Python, como el
modelo principal (pyodbc 5.3 ya trae versión para Python 3.14 en Windows). La conexión usa el controlador
`Microsoft Access Driver (*.mdb, *.accdb)`, que debe ser de los mismos bits que tu Python (casi siempre 64). Si la
revisión de arranque dice que no está, instala el *Microsoft Access Database Engine 2016 Redistributable* de 64 bits.

Qué cambia en los resultados respecto a correr con los CSV del área: los meses ya cerrados toman los índices `Real` de
HParametros (los de SAP), no los del presupuesto del año; los meses por venir toman nuestra proyección (y el IS (FA) en
40, 50, 80 y 90); el TC de los meses por venir es el pronóstico de Inversiones y no el promedio de los dos últimos meses.
