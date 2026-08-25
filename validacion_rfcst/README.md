# Validación RFCST 2026 (7+5)

Script de validación de las cifras del Reforecast 2026 que comparte el área de
Suscripción (pestaña `BD_RFCST26`, forecast acumulado a diciembre en las
columnas U:W), para Planeación Financiera.

## Uso

```
python VAL_RFCST26.py
```

El script busca `Inputs/BD_RFCST_26_act.xlsx` (o cualquier `BD_RFCST*.xlsx` en
`Inputs/` o junto al script). Para correrlo contra la carpeta de OneDrive,
ajustar la variable `xFolder` al inicio del script.

Requiere: `pandas`, `numpy`, `openpyxl`, `xlsxwriter`.

## Salidas (carpeta `Outputs/`)

| Archivo | Contenido |
|---|---|
| `VAL_RFCST26.xlsx` | Dashboard de KPIs, resumen por LN (con semáforos, score de riesgo y ranking), cortes por LN×Tipo Rea, fuente y país, excepciones, detalle contrato por contrato con todos los flags, y la hoja `Parametros` con los umbrales usados |
| `Dashboard_RFCST26.html` | Dashboard visual (abrir en el navegador): KPIs, primas por LN vs ppto y real 2025, incremento Ago-Dic forecast vs esperado, semáforo de contratos y top de excepciones |

## Validaciones

| # | Validación | Lógica |
|---|---|---|
| V1 | Consistencia acumulada | El forecast a Dic 2026 (U:W) no puede ser menor al real con corte a Julio 2026 (Q:S): el acumulado nunca decrece |
| V2 | Incremento Ago-Dic vs Ppto ajustado | Incremento implícito (FCST − Real Jul) comparado con el ppto Ago-Dic escalado por el nivel de ejecución Ene-Jul (Real Jul / Ppto Ene-Jul). Si a julio llevamos el doble de lo presupuestado, es razonable esperar ~el doble en Ago-Dic |
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
