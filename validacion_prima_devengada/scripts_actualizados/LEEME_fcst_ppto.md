# FCST y PPTO (RRC y SONR) con el FND del modelo

Planeación Financiera (BP&A) · Reaseguradora Patria · septiembre 2026

Son tus cuatro scripts **tal cual**, con sólo los dos cambios que pediste:

1. **El FND del proporcional y el facultativo sale del modelo** (`mec_devengamiento.py` + `delta_calibrado.json`, leídos de tu carpeta de Documents), detrás del interruptor `USAR_FND_CALIBRADO`. El no proporcional (TipoRea 2) no se toca.
2. **Las rutas de OneDrive quedan como las tuyas**, con `usuario = "asunad"` declarado desde el inicio del archivo, igual que en `ReforecastRRC_aod.py`.

Queries, filtros, fórmulas, constantes, nombres de columna y nombres de los archivos de salida: idénticos. El diff de cada uno está en `diffs\`.

## Rutas: de dónde a dónde

| Antes | Ahora |
|---|---|
| `…\Planeación Financiera RPAT - Documents\Financieros` (catálogos) | `…\Documents` |
| `…\Documentos\Planeación Financiera\Forecasts\2026\Programas\Inputs` | `…\Archivos de Maria Osmara Camacho Lopez - Inputs` |
| `…\Documentos\Planeación Financiera\Forecasts\2026\Programas\Outputs` | `…\Documents\Outputs` |
| `…\Planeación Financiera RPAT - Documents\Presupuestos\2026\…` (árbol de subcarpetas de los PPTO) | `…\Archivos de Maria Osmara Camacho Lopez - Inputs`, plano |
| `C:\Users\mocamachol\…\6_Recalibración\xls` (el `BD_CtaMens`) | `…\Archivos de Maria Osmara Camacho Lopez - Inputs` |
| `usuario = getpass.getuser()` | `usuario = "asunad"`, arriba del todo |

La base de valuación (`\\adsroma\…\BaseValuacion.accdb`) no cambió.

**Ojo con dos archivos de los PPTO.** Al aplanar el árbol de Presupuestos, los scripts ahora buscan todo en tu carpeta de Inputs. La mayoría ya la tienes ahí (`ParametrosMens2026.csv`, `TablaCesion.csv`, `Subramo.csv`, `FrecCol.csv`, `IS_Cat.csv`, `AFUN.csv`, `CesionPI.csv`, `zFrecuencias.csv`, `Cesion ID Esp.csv`), pero faltan dos que antes venían de otro lado:

- `Pais.csv` — no lo vi en tu carpeta.
- `BD_CtaMens_reservas_0526.xlsx` (PPTO_RRC) y `BD_CtaMens_0526.xlsx` (PPTO_SONR) — venían de la carpeta de Mónica. Necesitas una copia en tu Inputs, o cambiar esa línea de vuelta a su ruta si tienes acceso.

## Qué poner en Documents

Sólo dos archivos, además de los scripts:

| Archivo | Para qué |
|---|---|
| `mec_devengamiento.py` | módulo del MEC; lo importan los cuatro desde `C:\Users\asunad\OneDrive - GPV\Documents`. No se corre a mano |
| `delta_calibrado.json` | los δ por ramo. Usa el de `salidas\` de tu última validación, o el que viene aquí |

## El interruptor

Arriba de cada script, bloque `#%% FND CALIBRADO`:

    USAR_FND_CALIBRADO = True   # False -> comportamiento idéntico al script original (xPND)

- **`True`** — el FND del proporcional y el facultativo es la tabla calibrada por antigüedad de registro: `NT(k) − δ_ramo`, con `k` = mes de valuación − mes contable del registro.
- **`False`** — los diccionarios `xPND` / `xPND2` de siempre. El script se comporta exactamente como el tuyo.

Como no cambié los nombres de salida, los dos modos escriben el mismo archivo. **Renombra el output anterior antes de correr** para poder compararlos.

El mes de valuación se toma de donde corresponde en cada script: en los FCST, del ciclo (`Meses` en el RRC, `xFecVal` en el SONR); en los PPTO, de `zAñoMesPPTO`, que es el último mes de la ventana de `xPND`/`xPND2` (`xAños[Meses + 11]`) y por tanto la fecha a la que valúa el presupuesto.

## Por qué Incendio se mueve aunque su δ sea cero

Es la pregunta que traías, y tiene respuesta limpia. **δ de Incendio = 0.000**, así que `FND_modelo(k) = NT(k) − 0 = NT(k)`. Pero el FND anterior no era sólo `NT(k)`: era `xPND[CALMONTH][FRECUENCIA]`, es decir **una columna distinta según la periodicidad de la cuenta**. El modelo no distingue frecuencia —la absorbe dentro de δ— así que todas las cuentas del ramo toman la columna mensual.

Para una antigüedad de registro k cualquiera, la diferencia por frecuencia es constante:

| Frecuencia de la cuenta | FND anterior (k = 0) | FND del modelo | Diferencia |
|---|---|---|---|
| Mensual (`1` / `NA`) | 0.958904 | 0.958904 | **0.000000** |
| Bimestral (`2`) | 0.916667 | 0.958904 | +0.042237 |
| Trimestral (`3`) | 0.876712 | 0.958904 | +0.082192 |
| Semestral (`6`) | 0.753425 | 0.958904 | +0.205479 |
| Anual (`0`) | 0.506849 | 0.958904 | +0.452055 |

Las cuentas mensuales de Incendio dan **exactamente** el mismo FND que antes. Las que tienen periodicidad trimestral, semestral o anual suben, y como Incendio pesa un tercio de la RRC, ese cambio se ve en el total del ramo aunque su δ sea cero.

Esto es intencional, no un defecto: la calibración se hizo contra la RRC real **agregada por ramo**, y δ absorbe la mezcla de frecuencias que tenía la cartera. A nivel de ramo cuadra (Incendio: razón 0.997, error medio mensual 2.4%); a nivel de cuenta individual con frecuencia no mensual, sí se mueve. Si el área quiere conservar el escalonamiento por frecuencia, habría que recalibrar δ por ramo × frecuencia en vez de por ramo, que es un cambio de alcance del modelo, no de estos scripts.

## Un problema que trae `PPTO_RRC.py` de origen

No es del cambio que hice: viene así en el archivo que me pasaste. Con `zAñoReal = 2026` (línea 14), `Meses = 202613`, pero la tabla `xAños` (línea 58) sólo llega a `202524`. Al construir `xPND` en la línea 61 el script muere con `KeyError: 202613` antes de hacer nada.

`PPTO_SONR_.py` no tiene el problema porque ahí `zAñoReal = 2025` y `Meses = 202513`, que sí está en la tabla.

Para que `PPTO_RRC.py` corra hay que extender `xAños` al ejercicio 2027 (`202613 → 202701` … `202624 → 202712`) o mover `zAñoReal`. No lo toqué porque pediste no cambiar nada más, pero sin eso el script no arranca ni con el interruptor apagado.

## Lo que se verificó antes de entregarlo

- Comparación por AST del original contra el nuevo, archivo por archivo: los únicos nodos que cambian son el bloque del FND, `usuario`, las asignaciones de `xFolder`/lecturas y las funciones donde vivía la búsqueda en `xPND`. Ninguna query, filtro, fórmula ni constante.
- Todas las líneas borradas revisadas una por una: sólo rutas, `usuario` y las lambdas de `xPND`.
- `fnd_cal` de los tres scripts de tipo RRC reproduce `mec.fnd_registro` en los 11 ramos × 12 antigüedades; devuelve el legado con el interruptor apagado, con TipoRea 2 y con mes de valuación sin fijar; y 0 para registros futuros.
- FCST_RRC, malla de 288 filas (8 ramos × 3 tipos de reaseguro × 4 antigüedades × 3 combinaciones de vigencia): con `False`, cero diferencias contra el original; con `True`, el no proporcional idéntico (96 filas) y el proporcional igual a la tabla calibrada (192).
- FCST_SONR, 1,152 casos: con `False`, cero diferencias; con `True`, cero errores, no proporcional intacto y proporcional igual a la tabla.
- Finales de línea Windows (CRLF) y tabulaciones intactos; `py_compile` limpio en los cuatro.
