# Scripts del área (RRC y SONR) con los insumos de la BD proyectada

Versiones de `reforecastRRC_v10_Esc1_ocl.py` y `ReforecastSONR_v3.py` que toman sus parámetros de la BD proyectada
(`BD_ BEL - IRR - MR_Proyeccion.xlsx`, la salida de `proyeccion_reservas.py`) en lugar de los CSV de parámetros del
área y de las constantes del año. La lógica de valuación (consultas a la base, factores de no devengamiento, cesión,
margen de riesgo, método propio del SONR, escenarios) es la de los scripts originales; cada cambio está marcado en el
código con `### INSUMOS BD`.

| Archivo | Qué es |
|---|---|
| `insumos_bd.py` | Lee la BD proyectada y arma las tablas con la forma que esperan los scripts (abajo). Se puede correr solo: `python insumos_bd.py "<BD>" Parametros_usados.xlsx` escribe las tablas para revisarlas. |
| `reforecastRRC_v11_insumosBD.py` | RRC. Mismos escenarios 0 a 5 del original. |
| `ReforecastSONR_v4_insumosBD.py` | SONR. Mismos escenarios 0 a 4 del original. |
| `config_local.ejemplo.py` | Plantilla de la configuración local. Cópiala como `config_local.py` y pon tus rutas y parámetros. `config_local.py` no se versiona: lleva rutas internas y los parámetros de capital del margen de riesgo. |
| `pruebas/simulacion_sin_access.py` | Corre los dos scripts sin la base Access ni los archivos del área, con contratos y catálogos inventados, y comprueba que los índices que usan son los de la BD. Sirve para probar el código en cualquier equipo; sus montos no son reservas. |

## De dónde sale cada insumo

| Insumo del script | Antes | Ahora (`insumos_bd.py`) |
|---|---|---|
| `ParametrosMens` (RRC): `IS Bel Media-m`, `IS Bel 99.5%-m` | CSV del año | `HParametros`: `Ind Sin RRC` e `Ind sin RRC 99.5%` del mes de valuación `m`, renglones `Real` hasta el último mes real y `Proyección` después. En los ramos de `RAMOS_IS_FA` (40, 50, 80 y 90), en los meses proyectados, el IS (FA) de la hoja `IS_FA` (media y 99.5 %). |
| `Ind. Gasto` (RRC) | Un valor por ramo en el CSV | `Ind. Gasto-m`: el bloque `FACTOR GTO` (GTO / PND) del ramo y mes de valuación. El script toma el del mes que valúa (en el escenario 4, el de diciembre). |
| `Pesos_dur`, `Resto Monedas_dur`, `Pesos_ret`, `Resto Monedas_ret` (RRC, MR) | CSV del año | Siguen del CSV del área (`CSV_DURACION_RRC`): la BD no los trae. Sin el CSV, el MR del RRC no se puede calcular y el script lo avisa. |
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
   quieres, su `Diagnostico_Proyeccion.xlsx`).
2. Revisa en `config_local.py`: la base Access, los catálogos, las carpetas de CSV auxiliares de RRC y de SONR, el CSV
   con duración y retención (`ParametrosMens` del año), el presupuesto técnico del año y los parámetros del MR.
3. Corre `reforecastRRC_v11_insumosBD.py` y `ReforecastSONR_v4_insumosBD.py`. Escriben en `salidas_area/`:
   `RRC_esc.xlsx`, `SONR_esc.xlsx` (la misma forma de antes) y `Parametros_usados_<reserva>.xlsx` con las tablas de
   insumos que usaron (índices por mes, `IS_Cat`, `ParamSONR`, TC, escenario base y saldos proyectados) y los avisos.
4. Sin Access a la mano, `python pruebas/simulacion_sin_access.py "<BD>"` prueba que el código corre y toma los índices
   de la BD.

Qué cambia en los resultados respecto a correr con los CSV del área: los meses ya cerrados toman los índices `Real` de
HParametros (los de SAP), no los del presupuesto del año; los meses por venir toman nuestra proyección (y el IS (FA) en
40, 50, 80 y 90); el TC de los meses por venir es el pronóstico de Inversiones y no el promedio de los dos últimos meses.
