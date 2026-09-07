# Reforecast RRC y SONR (`_aod`) con el FND del modelo

Planeación Financiera (BP&A) · Reaseguradora Patria · septiembre 2026

Son tus dos scripts actuales —`ReforecastRRC_aod.py` y `ReforecastSONR_aod.py`— **tal cual**, con un solo cambio: el FND del proporcional y el facultativo sale del modelo (`mec_devengamiento.py` + `delta_calibrado.json`, leídos de tu carpeta de Documents), detrás del interruptor `USAR_FND_CALIBRADO`.

Todo lo demás está exactamente como lo tienes: las rutas de insumos (`Documents`, `Archivos de Maria Osmara Camacho Lopez - Inputs`), las de salida (`Documents\Outputs`), los nombres de los archivos que escribe (`RRC_esc.xlsx`, `SONR_esc.xlsx`, los intermedios), `usuario = "asunad"`, queries, filtros, constantes. El no proporcional (TipoRea 2) tampoco se toca. El diff de cada uno está en `diffs\`.

## Qué poner en Documents

Sólo dos archivos, junto a los scripts:

| Archivo | Para qué |
|---|---|
| `mec_devengamiento.py` | módulo del MEC; lo importan los dos desde `C:\Users\asunad\OneDrive - GPV\Documents`. No se corre a mano |
| `delta_calibrado.json` | los δ por ramo. Usa el de `salidas\` de tu última validación, o el que viene aquí |

Y reemplazar tus dos scripts por estos. Se corren igual que siempre.

## El interruptor

Arriba de cada script, bloque `#%% FND CALIBRADO`:

    USAR_FND_CALIBRADO = True   # False -> comportamiento idéntico al script original (xPND)

- **`True`** — el FND del proporcional y el facultativo es la tabla calibrada por antigüedad de registro: `NT(k) − δ_ramo`, con `k` = mes de valuación − mes contable del registro.
- **`False`** — los diccionarios `xPND` de siempre. El script se comporta exactamente como el tuyo.

**Ojo con la salida.** Como no cambié ni la ruta ni el nombre, los dos modos escriben el mismo `Documents\Outputs\RRC_esc.xlsx` (y `SONR_esc.xlsx`). Para poder comparar, **renombra el que ya tienes antes de correr** (por ejemplo a `RRC_esc_anterior.xlsx`), o copia el nuevo a otro nombre en cuanto termine.

## Cómo comparar contra el output anterior

Con `comparar_outputs_reservas.py` en la misma carpeta que los dos archivos:

    python comparar_outputs_reservas.py RRC_esc_anterior.xlsx RRC_esc.xlsx RRC
    python comparar_outputs_reservas.py SONR_esc_anterior.xlsx SONR_esc.xlsx SONR

Escribe `Comparativo_RRC.xlsx` y `Comparativo_SONR.xlsx` (Resumen, Por_ramo, Por_periodo, Detalle; diferencia = nuevo − base; rojo arriba de 2%).

Prueba de control que vale la pena hacer primero: corre con `False`, compara contra tu output anterior y todo debe dar cero. Luego con `True`: eso es el efecto puro del FND del modelo.

## Lo que se verificó antes de entregarlo

- Comparación por AST del original contra el nuevo: los únicos nodos que cambian son el bloque del FND y las funciones donde vive la búsqueda en `xPND` (`ConsultaReal`, `ConsultaReal_USD`; en el SONR también `zFND`, `zFND2`, `zFND_PPTO`). Rutas, nombres de salida, queries, filtros y fórmulas, idénticos.
- Con el interruptor en `False`, las funciones del FND del SONR reproducen las originales en 1,296 casos (tres tipos de reaseguro × cuatro combinaciones de vigencia × registros de 10 años a hoy × seis frecuencias). Cero diferencias.
- Con `True`: cero errores, el no proporcional idéntico al original en 432 casos, el proporcional igual a la tabla calibrada en 864.
- En el RRC, el CAT no proporcional (ramos 71/73 con TipoRea 2) conserva el valor de siempre: `fnd_cal` recibe el TipoRea y devuelve el legado cuando es 2. Hacía falta porque la jerarquía original de `PORC_ND` mira «Ramo in [71,73]» antes que TipoRea 2, y sin esa guarda el CAT XL habría tomado la tabla calibrada, que sólo se ajustó sobre el proporcional. Lo encontró la revisión adversarial; está probado contra el original.
- Finales de línea Windows (CRLF) y tabulaciones intactos; `py_compile` limpio.
- Revisión adversarial independiente por dos lentes (alcance del cambio; corrección del interruptor y la integración) por archivo.

Cuatro cosas que conviene saber al leer los resultados con el interruptor en `True`:

- El CAT **proporcional y facultativo** (ramos 71/73 con TipoRea 1 o 3) sí cambia: el original les daba la columna `NA` de `xPND` (la frecuencia se fuerza a `NA` para 71/73) y ahora toman la tabla calibrada del ramo 70, con su δ de −0.035. Es parte del cambio pedido —es proporcional— y es coherente con la calibración, que ajustó el δ de CAT sobre ese mismo tramo. El CAT **no proporcional** (TipoRea 2) queda intacto, como el resto del no proporcional.
- Las cuentas proporcionales o facultativas **sin fechas de vigencia** (IniVig = FinVig = 0 tras el `fillna`) ya no van por la regla 0/1 del original sino por la tabla calibrada según su mes de registro. Es lo que dice el modelo: el FND del proporcional depende del mes en que se registra la cuenta, no de la vigencia.
- En el SONR, las filas fijas de `xPND` (`202606`, `202706`, …) dejan de aplicar al proporcional. En el original la llave `202606` estaba repetida y la fila fija pisaba a la del mes, así que en junio usaba 0.4986 en lugar de 0.9589; eso explica una diferencia visible en junio.
- `mec_devengamiento.py` tiene que estar en Documents aunque el interruptor esté en `False`: el import es incondicional. Si falta, el script muere en el import.

Un detalle que salió de esa prueba: el primer parche evaluaba el valor legado de `xPND` antes de tiempo, y como el SONR lee diez años de registros, con el interruptor encendido habría reventado en la primera fila de más de doce meses. Corregido aquí y en la v4 que te había mandado antes.
