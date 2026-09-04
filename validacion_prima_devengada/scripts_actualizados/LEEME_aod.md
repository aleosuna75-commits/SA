# Reforecast RRC y SONR (`_aod`) con el FND del modelo, corriendo desde Documents

Planeación Financiera (BP&A) · Reaseguradora Patria · septiembre 2026

Son tus dos scripts actuales —`ReforecastRRC_aod.py` y `ReforecastSONR_aod.py`— **tal cual**, con exactamente dos cambios:

1. **El FND del proporcional y el facultativo sale del modelo** (`mec_devengamiento.py` + `delta_calibrado.json`), detrás del interruptor `USAR_FND_CALIBRADO`. El no proporcional (TipoRea 2) no se toca.
2. **Todas las rutas apuntan a la carpeta del script.** Insumos y salidas, en Documents. Ya no hay `C:\Users\asunad\...` en el código.

Nada más cambió: ni queries, ni filtros, ni constantes, ni nombres de archivo de entrada (`ParametrosMensPPTO_3+9.csv`, `ParamSONR2026_3+9.csv`, etc. siguen igual). El diff completo de cada uno está en `diffs\`.

## Qué poner en Documents

Junto a tus CSV y al `CentralizadoCatálogos_SIRECySAP.xlsx` que ya tienes ahí:

| Archivo | Para qué |
|---|---|
| `ReforecastRRC_aod.py` | reemplaza al tuyo |
| `ReforecastSONR_aod.py` | reemplaza al tuyo |
| `mec_devengamiento.py` | módulo del MEC; lo importan los dos. No se corre a mano |
| `delta_calibrado.json` | los δ por ramo. Usa el de `salidas\` de tu última validación, o el que viene aquí |
| `comparar_outputs_reservas.py` | para el paso 4, comparar contra el output anterior |

Se corren igual que siempre: `python ReforecastRRC_aod.py` y `python ReforecastSONR_aod.py`.

## El interruptor

Arriba de cada script, bloque `#%% FND CALIBRADO`:

    USAR_FND_CALIBRADO = True   # False -> comportamiento idéntico al script original (xPND)

| Valor | FND del proporcional/facultativo | Salida |
|---|---|---|
| `True` | tabla calibrada por antigüedad de registro: `NT(k) − δ_ramo`, con `k` = mes de valuación − mes contable del registro | `RRC_esc_FNDcal.xlsx` / `SONR_esc_FNDcal.xlsx` |
| `False` | los diccionarios `xPND` de siempre; el script se comporta exactamente como el tuyo | `RRC_esc_legado.xlsx` / `SONR_esc_legado.xlsx` |

El nombre de la salida cambia a propósito, para no pisar tu `RRC_esc.xlsx` / `SONR_esc.xlsx` de `Documents\Outputs` y poder cruzarlos. Los intermedios (`ConsultaR_RRC_<mes>.xlsx`, `ConsultaPPTO_RRC_<mes>_tradicional.xlsx`, `TablaTCRRC.xlsx`, `TablaTCSONR.xlsx`, `auxSONR_sum.xlsx`) también quedan en Documents.

## Cómo comparar contra el output anterior

1. Corre los dos con `False`. Copia tu `RRC_esc.xlsx` y `SONR_esc.xlsx` de `Documents\Outputs` a Documents y corre:

       python comparar_outputs_reservas.py RRC_esc.xlsx RRC_esc_legado.xlsx control
       python comparar_outputs_reservas.py SONR_esc.xlsx SONR_esc_legado.xlsx control

   Todas las diferencias deben ser cero. Es la prueba de que los cambios de ruta no movieron nada.

2. Corre los dos con `True` y:

       python comparar_outputs_reservas.py

   Sin argumentos busca `RRC_esc.xlsx` vs `RRC_esc_FNDcal.xlsx` y `SONR_esc.xlsx` vs `SONR_esc_FNDcal.xlsx`, y escribe `Comparativo_RRC.xlsx` y `Comparativo_SONR.xlsx` (Resumen, Por_ramo, Por_periodo, Detalle; diferencia = nuevo − base; rojo arriba de 2%). Eso es el efecto puro del FND del modelo.

## Lo que se verificó antes de entregarlo

- Comparación por AST del original contra el nuevo: los únicos nodos que cambian son el bloque del FND, las asignaciones de `xFolder`, `fileName`, y las funciones donde vive la búsqueda en `xPND` (`ConsultaReal`, `ConsultaReal_USD`; en el SONR también `zFND`, `zFND2`, `zFND_PPTO`). Ninguna query, filtro ni fórmula.
- Con el interruptor en `False`, las funciones del FND del SONR reproducen las originales en 1,296 casos (tres tipos de reaseguro × cuatro combinaciones de vigencia × registros de 10 años a hoy × seis frecuencias). Cero diferencias.
- Con `True`: cero errores, el no proporcional idéntico al original en 432 casos, el proporcional igual a la tabla calibrada en 864.
- Finales de línea Windows (CRLF) y tabulaciones intactos; `py_compile` limpio; ninguna ruta `C:\Users` activa.
- Revisión adversarial independiente por dos lentes (alcance del cambio; corrección del interruptor y la integración) por archivo.

Un detalle que salió de esa prueba y que conviene saber: el primer parche evaluaba el valor legado de `xPND` antes de tiempo, y como el SONR lee diez años de registros, con el interruptor encendido habría reventado en la primera fila de más de doce meses. Corregido aquí y en la v4 que te había mandado antes.
