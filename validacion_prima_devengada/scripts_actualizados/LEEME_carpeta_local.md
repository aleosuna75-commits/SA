# Cómo correr todo desde tu carpeta local (Documents)

Planeación Financiera (BP&A) · Reaseguradora Patria · septiembre 2026

Todos los scripts se anclan a **su propia carpeta**: leen los insumos de ahí y escriben las salidas ahí mismo. No hay rutas de usuario dentro del código. Basta con copiar los scripts y los archivos que cada uno pide a la misma carpeta (por ejemplo `C:\Users\<tú>\OneDrive - GPV\Documents`) y correrlos desde donde sea:

    python nombre_del_script.py

Si prefieres otra carpeta para los reforecast, la constante `CARPETA` al inicio de cada uno admite una ruta completa. La base de valuación (`BaseValuacion.accdb`) se sigue leyendo del servidor `\\adsroma` por ODBC; eso no cambió.

Requisitos: Python 3.9+ con `pandas`, `numpy`, `openpyxl` (y `pyodbc` para los reforecast, `pyxlsb` sólo si vas a leer Integración Dim en `.xlsb`).

## Qué se corre y qué no

Sólo cinco archivos se **corren**. El resto son módulos que los scripts importan solos, o archivos de consulta.

| Archivo | ¿Se corre? | Qué hace |
|---|---|---|
| `construir_input_mec.py` | sí, paso 1 | arma el input del MEC |
| `generar_output_mec.py` | sí, paso 1b | arma el output del MEC a partir de ese input |
| `preparar_insumos.py` + `validar_prima_devengada.py` | sí, paso 2 | validan el FND contra la RRC real y recalibran los δ |
| `reforecastRRC_v11_Esc1_ocl.py` y `ReforecastSONR_v4.py` | sí, paso 3 | las dos reservas |
| `comparar_outputs_reservas.py` | sí, paso 4 | compara el output nuevo contra el anterior |
| `mec_devengamiento.py` | **no** | módulo del MEC; lo importan solos el output del MEC y los dos reforecast. Nunca se corre a mano. |
| `delta_calibrado.json` | **no** | los δ por ramo; lo leen los anteriores |
| `fnd_calibrado.py` | **no hace falta** | módulo de consulta. Corrido a mano sólo imprime los δ y la tabla FND en pantalla; no lee ni escribe archivos y no tiene interruptor. Si lo borras no se rompe nada. |
| `verificar_excel_formulas.py` | opcional | comprueba las fórmulas del Excel de validación |

## Dónde está el interruptor `True` / `False`

No está en `fnd_calibrado.py`. Está arriba de cada script que produce un resultado, en el bloque comentado `#%% FND CALIBRADO`:

| Archivo | Línea (aprox.) | Constante | Gobierna |
|---|---|---|---|
| `reforecastRRC_v11_Esc1_ocl.py` | 46 | `USAR_FND_CALIBRADO = True` | la RRC |
| `ReforecastSONR_v4.py` | 33 | `USAR_FND_CALIBRADO = True` | el SONR |
| `mec_devengamiento.py` | 116 | `ConfigMEC.USAR_CALIBRADO = True` | el output del MEC |

Se cambia editando esa línea en el archivo, con el bloc de notas o con VS Code, y volviendo a correr el script. No hay parámetro por línea de comandos.

**Qué cambia:**

- **`True`** — el factor de no devengamiento del proporcional y el facultativo sale de la tabla calibrada, indexada por **antigüedad de registro**: `FND = NT(k) − δ_ramo`, con `k` = mes de valuación − mes contable del registro, y δ el desplazamiento del ramo. Es lo que cuadra con la RRC real (razón 0.989, error medio mensual 3.1%). El no proporcional no cambia: sigue con la prorrata exacta por fechas de vigencia.
- **`False`** — el factor sale de donde salía antes: los diccionarios `xPND` / `xPND2` que están escritos dentro del propio script, indexados por `CALMONTH` y por la frecuencia de la cuenta. Es decir, el script se comporta **exactamente** como la v10 (RRC) o la v3 (SONR).

Los `False` no son para producción: son el control. Corres primero con `False` para confirmar que la versión nueva reproduce la anterior al centavo, y ya con esa certeza corres con `True` para ver el efecto puro del FND del modelo. Por eso la salida se llama distinto en cada caso.

## 1. Input del MEC · histórico actualizado a julio + presupuesto agosto–diciembre

| Pon en la carpeta | Qué es |
|---|---|
| `construir_input_mec.py` | el script |
| `BD_PptoTécnicoRPAT_GENERADA.xlsx` | la BD histórica del MEC, ya actualizada a julio 2026 (cualquier nombre que empiece con `BD_Ppto` o contenga `Tecnico`/`Técnico` y `RPAT` sirve) |
| `FCST2026.xlsx` | el reforecast 2026 (hoja `Ppto2026`, en USD) |
| `tc_mensual_bd.csv` | opcional: TC de cierre por mes para pasar el FCST a pesos; si falta usa la tabla `TC_MENSUAL` del script |

Corre `python construir_input_mec.py`. El script busca **primero** la BD histórica y sólo si no la encuentra usa `BDReal26.xlsx`. Toma de la BD todo hasta `FRONTERA_REAL = 202607`, descarta lo que traiga después de esa fecha (regla `V20`, por si la BD ya trae agosto parcial) y completa `VENTANA_PPTO = (202608, 202612)` con el FCST. Las dos constantes están al inicio del script; en cada cierre se mueve la frontera un mes.

Salidas en la misma carpeta:

- `Input_MEC_Devengamiento.xlsx` (hojas Input, Cobertura, Validaciones)
- `TriangulosPrimaDevengada.csv`
- `Registros_Vigencia_MEC.csv` — con la BD histórica sí se regenera, porque cubre más de 24 meses de registro (`MESES_MIN_VIGENCIAS`); con `BDReal26.xlsx` sola se guardaría aparte para no degradar la curva PF+.

La cohorte de cada fila es su **mes contable** (cuando entra el movimiento), tanto en el FCST como en las fuentes alternas; el año de suscripción queda en la columna `AñoSusc` sólo como dato descriptivo. Revisa la hoja Validaciones: `V17` dice qué meses aportó cada fuente y si el año quedó sin huecos; `V9` compara el FCST contra el real en los meses ya conocidos.

## 2. Validación del FND contra la prima devengada real

| Pon en la carpeta | Qué es |
|---|---|
| `preparar_insumos.py`, `validar_prima_devengada.py`, `fnd_calibrado.py`, `verificar_excel_formulas.py` | los scripts |
| `mec_devengamiento.py` | el módulo del MEC (v3); `preparar_insumos.py` lo usa para la curva PF+ |
| `BD_ BEL - IRR - MR.xlsx` | la base real de saldos (hojas `BD_Montos_RRC_SONR` y `HParametros_2026`) |
| `Input_MEC_Devengamiento.xlsx` | el input del paso 1 (o el que quieras validar) |
| `Registros_Vigencia_MEC.csv` | las vigencias del paso 1 |
| `Integración*.xlsb` **o** `er_real_primas.csv` | el % cedido por ramo del ER real; si tienes el `.xlsb` se extrae solo (`pip install pyxlsb`), si no, con el CSV de esta entrega basta |

Corre en este orden:

1. `python preparar_insumos.py` → crea la subcarpeta `insumos\` con `real_rrc_long.csv`, `is_rrc_real.csv`, `tc_mensual_bd.csv`, `input_mec_bd.csv`, `mec_vectores_h72.csv`, `er_real_primas.csv`. Detecta solo el último mes con saldo en la base real.
2. `python validar_prima_devengada.py` → crea `salidas\` con `Validacion_Prima_Devengada.xlsx`, los CSV y `delta_calibrado.json` (los δ recalibrados con la base que le des).
3. Opcional: `python verificar_excel_formulas.py` → comprueba que las fórmulas ámbar de la hoja Mensual reproducen los valores de Python. Recalcula con LibreOffice si lo tienes instalado; si no, sólo revisa que las fórmulas apunten a las columnas correctas y te pide abrir el archivo en Excel.

En el Excel, la columna `Año` es siempre el **año contable** (el mes de valuación de la RRC, `PERIODO // 100`), nunca el de suscripción. Las columnas en azul son la prima no devengada real (`PND_real`) y la del modelo calibrado con la que se compara (`PND_CAL`); las columnas en ámbar traen fórmulas vivas de Excel (prima retenida, RRC bruta y neta del modelo, variaciones y prima devengada tomada y retenida, real y modelo). La hoja `Formulas` explica cada una.

## 3. Reforecast RRC y SONR con el FND del modelo

| Pon en la carpeta | Qué es |
|---|---|
| `reforecastRRC_v11_Esc1_ocl.py` | reemplaza a la v10 |
| `ReforecastSONR_v4.py` | reemplaza a la v3 |
| `mec_devengamiento.py` | módulo del MEC v3 (el mismo de arriba) |
| `delta_calibrado.json` | los δ por ramo; toma el de `salidas\` del paso 2 (o el de esta carpeta) |
| Insumos del RRC | `CentralizadoCatálogos_SIRECySAP.xlsx` · `LlavesPol.csv` · `ParametrosMens2025.csv` · `IS_Cat.csv` · `AjManuales.csv` · `ParametrosMensPPTO2025.csv` · `IS_Cat_PPTO.csv` · `Escenario_base_RRC.csv` · `Subramo.csv` · `CesionPI.csv` · `AFUN.csv` · `zFrecuencias.csv` · `TablaCesion_Esc1.csv` · `Cesion ID Esp.csv` · `PptoTecnico2025.csv` |
| Insumos del SONR | `AjManuales_SONR.csv` · `Subramo.csv` · `TablaBase_MetodoPropio.csv` · `TablaBase_MetodoPropio_ext.csv` · `ParamSONR2025.csv` · `ParamSONR2025_lagsinc.csv` · `PNDmes.csv` · `FrecCol.csv` · `LlavesPol.csv` · `Escenario_base_SONR.csv` · `PptoTecnico2025.csv` |

Son exactamente los archivos que los scripts ya leían de las distintas carpetas de OneDrive; sólo cambia que ahora viven todos juntos. El único cambio de resultado es el FND: con `USAR_FND_CALIBRADO = True` (valor por defecto) el proporcional y el facultativo usan la tabla calibrada por antigüedad de registro y el no proporcional sigue con la prorrata exacta; con `False` los scripts se comportan igual que la v10 y la v3.

El nombre de la salida dice con qué factor se corrió, para que no pise el output anterior:

| Script | Interruptor | Salida |
|---|---|---|
| RRC v11 | `True` | `RRC_esc_FNDcal.xlsx` |
| RRC v11 | `False` | `RRC_esc_legado.xlsx` (debe dar igual que `RRC_esc.xlsx` de la v10) |
| SONR v4 | `True` | `SONR_esc_FNDcal.xlsx` |
| SONR v4 | `False` | `SONR_esc_legado.xlsx` (debe dar igual que `SONR_esc.xlsx` de la v3) |

Los archivos intermedios (`ConsultaR.xlsx`, `ConsultaPPTO_RRC_<mes>_tradicional.xlsx`, `TablaTCSONR.xlsx`, `ConsultaR_USD<mes>_E4.xlsx`, `auxSONR_sum.xlsx`) también quedan en la carpeta, como antes.

## 4. Comparar el output nuevo contra el anterior

Copia a la carpeta el `RRC_esc.xlsx` y el `SONR_esc.xlsx` de la última corrida con los scripts anteriores, y corre:

    python comparar_outputs_reservas.py

Busca los pares `RRC_esc.xlsx` vs `RRC_esc_FNDcal.xlsx` y `SONR_esc.xlsx` vs `SONR_esc_FNDcal.xlsx` y escribe `Comparativo_RRC.xlsx` y `Comparativo_SONR.xlsx` con cuatro hojas: Resumen (tipo de monto × escenario), Por_ramo, Por_periodo (escenario 2) y Detalle (cruce completo por llave, con lo que sólo está en un lado). La diferencia es siempre nuevo − base, en pesos y en dólares, y las celdas con más de 2% quedan en rojo.

Para comparar cualquier otro par: `python comparar_outputs_reservas.py <base.xlsx> <nuevo.xlsx> [etiqueta]`. Por ejemplo, para confirmar que la v11 con el interruptor apagado reproduce la v10: `python comparar_outputs_reservas.py RRC_esc.xlsx RRC_esc_legado.xlsx legado` (todas las diferencias deben ser cero). `--demo` arma un par sintético y verifica el comparador solo.

## Orden sugerido

1. Paso 1 con tu BD actualizada a julio → input 2026 completo.
2. Paso 2 → confirmar que el FND sigue cuadrando con la base real y tomar el `delta_calibrado.json` fresco.
3. Paso 3 con `USAR_FND_CALIBRADO = False` → comparar contra el output anterior con el paso 4: deben ser idénticos.
4. Paso 3 con `True` → el comparativo del paso 4 muestra el efecto puro del FND del modelo.
