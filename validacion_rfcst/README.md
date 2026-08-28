# Validación RFCST 2026 (7+5)

Script de validación de las cifras del Reforecast 2026 que comparte el área de
Suscripción (pestaña `BD_RFCST26`, forecast acumulado a diciembre en las
para Planeación Financiera. La cardinalidad Contrato / Cedente / MGA se deriva
de la columna `Fuente/Hoja`; el P-S-C (Primas − Siniestros − Costos) se reporta
con la nota de que falta el incremento a la reserva y los costos de cobertura.

## Uso

```
python VAL_RFCST26.py
```

`VAL_RFCST26.py` es autocontenido: es el unico archivo que necesitas copiar.
Busca `Inputs/BD_RFCST.xlsx` (o cualquier `BD_RFCST*.xlsx` en `Inputs/`
o junto al script) y escribe los resultados en `Outputs/`, siempre relativo a
la carpeta donde vive el script, sin importar desde donde lo ejecutes. Para correrlo contra la carpeta de OneDrive,
ajustar la variable `xFolder` al inicio del script.

Requiere: `pandas`, `numpy`, `openpyxl`, `xlsxwriter`. Para instalarlos:

```
pip install -r requirements.txt
```

Si falta alguno, el script avisa al inicio con el comando exacto en vez de
tronar a medio proceso.

## Fuente del presupuesto

Las **cifras globales** (sección General) toman el presupuesto de la hoja
`Ppto2026` del mismo libro, porque `BD_RFCST26` solo trae presupuesto de los
contratos que ya registraron prima y subestima el total. El script detecta la
hoja, la fila de encabezados, la columna de ejercicio (para acotar a 2026) y la
de periodo (para separar Ago-Dic), e imprime en consola lo que encontró. Si la
hoja no está, avisa y usa el presupuesto de `BD_RFCST26`. La fuente utilizada se
muestra en el subtítulo de la sección General y en la hoja `Parametros`.

El presupuesto global incluye **todas las líneas presupuestadas**, aunque
alguna todavía no tenga forecast, para que el global cuadre con el presupuesto de
la compañía. Hoy `LN04009` (DUL-Marine, 216.2 M) está presupuestada pero aún no
entrega forecast: esos millones no tienen contraparte en el RFCST y ensanchan la
brecha contra presupuesto, así que se reportan en la consola al ejecutar y en la
hoja `Ppto_Sin_Forecast` del Excel. El script identifica esas LN con la
columna `LN2` de la hoja (que incluye `LN04008-Agro` y empata con la `LN` del
forecast). Para comparar solo contra las LN que sí traen forecast, poner
`PPTO_SOLO_LN_CON_FCST = True` al inicio del script.

Los nombres de columna se configuran al inicio del script (`COL_PPTO`,
`COLS_ANIO`, `COLS_PERIODO`, `COLS_LN_PPTO`). Las **gráficas por línea de
negocio** siguen usando el presupuesto de `BD_RFCST26` sin cambios.

## Salidas (carpeta `Outputs/`)

| Archivo | Contenido |
|---|---|
| `VAL_RFCST26.xlsx` | Dashboard de KPIs, `Resumen_Global` con P/S/C y P-S-C (para el correo del reporte), resumen por LN (con semáforos, score, ranking, variaciones y gaps de las tres medidas, P-S-C/%P-S-C y participaciones, estilo ANA_RFCST), cortes por cardinalidad, LN×Tipo Rea, fuente, país, corredor, compañía, binder y contrato, `Pareto_Gap` por LN×compañía, excepciones, detalle contrato por contrato con todos los flags, y la hoja `Parametros` con los umbrales usados |
| `Dashboard_RFCST26.html` | Dashboard PRISMA (abrir en el navegador, no requiere internet). **General**: KPIs de Primas / Siniestros / Costos (FCST vs Ppto, crecimiento vs Real 2025, incremento Ago-Dic) y bloque P-S-C / %P-S-C con su nota. **Línea de Negocio**: las mismas vistas por LN en gráficas. **Contrato / Cedente / MGA**: filtros interactivos en cascada (LN, tipo de reaseguro, país, corredor, compañía, contrato o binder según el nivel) que actualizan la gráfica FCST 26 vs Ppto 26 vs Real 25, el semáforo, las entidades con alerta, el resumen por LN y el top de excepciones.
Incluye un botón **Imprimir PDF** al final que imprime únicamente la sección **Línea de Negocio** conservando el tema oscuro del dashboard, en A4 horizontal y sin márgenes blancos |

## Validaciones

| # | Validación | Lógica |
|---|---|---|
| V1 | Consistencia acumulada | El forecast a Dic 2026 no puede ser menor al real con corte a Julio 2026 (el acumulado nunca decrece), y el incremento Ago-Dic que trae la base debe cuadrar con (Dic − Jul) |
| V2 | Incremento Ago-Dic vs Ppto Ago-Dic | El incremento que el forecast proyecta para agosto-diciembre se compara contra lo presupuestado para ese mismo periodo. El nivel de ejecución Ene-Jul se conserva como columna de contexto (`Ratio_Ejecucion`) |
| V3 | Coherencia vs Reales 2025 | Crecimiento del forecast vs cierre 2025 y del incremento Ago-Dic vs el mismo periodo 2025, comparado contra el factor de incremento del Ppto |
| V4 | Índices técnicos vs factores | Siniestralidad y costos implícitos del forecast contra los factores históricos y de presupuesto (AS:AY) |
| V5 | Forecast vs Ppto anual | Cumplimiento, variación y gap contra el presupuesto 2026 año completo |
| V6 | Calidad de datos | Primas negativas, forecast en cero con real a julio, prima sin presupuesto, contratos sin factores, siniestralidad > 100%, siniestros netos negativos |

## Semáforos y score

- **ROJO**: inconsistencia dura (V1, prima negativa, FCST en cero,
  siniestralidad > 100%) en un contrato **material** (prima > $10k USD).
- **AMARILLO**: contrato material con alertas suaves (desviaciones de
  incremento, índices fuera de rango, faltantes de ppto/factores).
- **VERDE**: sin alertas o por debajo de materialidad.

El score de riesgo por LN (0-100) pondera: desviación del incremento Ago-Dic
(30%), siniestralidad del forecast (30%), coherencia vs 2025 (25%) y costos
(15%). Todos los umbrales y pesos están al inicio del script y quedan
documentados en la hoja `Parametros` del Excel de salida.

Los índices por LN se calculan sobre agregados (suma de siniestros / suma de
primas), no como promedio de razones por contrato.
