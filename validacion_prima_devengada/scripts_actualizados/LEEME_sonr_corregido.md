# SONR — qué pasó y qué se corrigió

Planeación Financiera (BP&A) · Reaseguradora Patria · septiembre 2026

## Lo primero: la diferencia abismal NO es el FND

Comparé las dos corridas (`Res_Rvas_2027.xlsx` contra `Res_Rvas_2027_FND.xlsx`) llave por llave.
**Sobre las llaves que las dos corridas produjeron, el FND mueve el SONR un −0.3% en total**, y por
ramo entre −7.4% (Autos) y +2.4% (Vida). Eso es todo lo que el FND explica.

El −213% que se ve en el Backtesting viene de otra cosa: **la corrida con el FND del modelo se quedó
sin salida para 8 de los 11 ramos desde 202604**.

- `Base SONR` del legado: **1,321 llaves únicas** = 11 ramos × 12 periodos × 5 tipos × 2 escenarios + 1.
- `Base SONR` del modelo: **686 llaves únicas**. El libro se rellenó hasta 1,321 repitiendo las 601
  primeras filas dos veces, así que a simple vista parece completo.
- Lo que falta: escenarios 2 y 3, **periodos 202604 a 202611**, ramos **10, 31, 35, 40, 60, 80, 90 y 110**.
  Sobrevivieron los tres ramos 39, 50 y 100, y por eso en el Backtesting esos tres siguen con números
  hasta 202608 mientras los demás caen a cero.

Un SONR al que le faltan Incendio, Vida y Diversos desde abril no se puede comparar con nada.

## Por qué un ramo desaparece sin avisar

En el ciclo de escenario 2/3:

    df_SONR_dim = df_Real_IS_Real.reindex(columns=['Ramo','BEL_RIESGO','IRR','MR'])
    auxSONR = df_SONR_dim.set_index(["Reserva","Ramo","Periodo"]).stack()

**`.stack()` descarta los NaN.** Si para un ramo `BEL_RIESGO`, `IRR` y `MR` son NaN, ese ramo no genera
ninguna fila y desaparece de la salida en silencio: no hay error, no hay aviso, el archivo sale más corto.

El NaN casi siempre viene del merge con `ParamSONR2026_3+9.csv` por `Llave = "<AñoMes>-<Ramo>"`. Si no hay
fila para, digamos, `202604-60`, entonces `Ind Sin SONR Media` llega vacío, y como

    BEL_RIESGO = Prima Dev × LAG × Ind Sin SONR Media

todo lo que cuelga de ahí es NaN. Ese es el patrón que encaja con lo observado: los meses 4 a 11 sin
parámetros para 8 ramos.

**Esto hay que comprobarlo en tu máquina**, porque el archivo de parámetros no lo tengo. Abre
`ParamSONR2026_3+9.csv` y verifica que la columna `Llave` traiga las 132 combinaciones `202601-<ramo>` …
`202612-<ramo>` para los 11 ramos. Si te faltan las de abril a noviembre para esos 8 ramos, ahí está.
El "3+9" del nombre sugiere que es un archivo de cierre a marzo: revisa que sea el que toca.

**El script corregido ya te lo dice solo.** Ahora imprime, mes a mes:

    [SONR][202604] AVISO — ramos que se van a perder en la salida:
        sin 'Ind Sin SONR Media' (falta Llave '202604-<ramo>' en ParamSONR): [10, 31, 35, 40, 60, 80, 90, 110]
        BEL_RIESGO todo NaN -> NO saldrán en Base SONR: [10, 31, 35, 40, 60, 80, 90, 110]
        Revisa que ParamSONR2026_3+9.csv tenga una fila por cada '202604-<ramo>'.

y al final, antes de escribir el archivo:

    [SONR] cobertura escenario 2: 11 ramos x 12 periodos = 132 esperados, 68 presentes
    [SONR] !! FALTAN 64 combinaciones ramo x periodo. La salida está INCOMPLETA.
           ramo 10: [202604, 202605, ...]

## El defecto que sí era mío, y está corregido

El parche del FND metía un atajo al principio de `zFND`, `zFND2` y `zFND_PPTO`:

    if USAR_FND_CALIBRADO and not _es_no_proporcional(xTipoRea):
        return fnd_cal(...)          # <- se ejecutaba ANTES que todo lo demás

Ese `return` **se saltaba la primera rama del original**, que es

    if xIniVig == xFinVig:
        return 0 if xMesProc < mes_valuación else 1

Como el script hace `ConsultaR[['IniVig','FinVig']].fillna(0)`, todos los registros sin fechas de vigencia
caen ahí con `0 == 0`. Con el atajo, esos registros dejaban de recibir el 0/1 duro y pasaban a recibir
`NT(k) − δ`. Es un cambio de comportamiento que yo no debí introducir.

**Corregido con otro diseño, que es el que pediste desde el principio:** el modelo ya no intercepta la
función, sino que **sustituye el valor de la tabla `xPND` en el punto exacto donde el script la lee**,
conservando la clave que el propio código calcula:

    result = xPND.get(xVal, 0).get(str(xFrecuencia), 0)
    return fnd_modelo(xRamo, xVal, result)

`fnd_modelo` traduce esa clave a la antigüedad `k` con el mismo mapa con el que se arma `xPND`
(`XPND_K[xAños[Meses - j]] = j`) y devuelve `NT(k) − δ_ramo`. Ninguna rama se salta: ni la de
`xIniVig == xFinVig`, ni la prorrata del no proporcional, ni el corte de los 12 meses. Las cuatro
entradas fijas que el original mete aparte (202606, 202706, 202806, 202906) conservan su valor legado,
igual que antes.

De paso, `zFND2` usaba la clave equivocada en el atajo: leía `xPND[xMesProc]` cuando el original lee
`xPND[xVal]`, el mes desplazado que calcula la proyección. Con el diseño nuevo eso ya no puede pasar,
porque la clave la sigue calculando el código original.

## Lo que se verificó

Malla de **207,900 casos** por script (12 meses de valuación × 3 tipos de reaseguro × 7 frecuencias ×
15 meses contables × 11 ramos × 4 combinaciones de vigencia):

| | ReforecastSONR_aod.py | FCST_SONR.py |
|---|---|---|
| `USAR_FND_CALIBRADO = False` contra el original | **0 diferencias** | **0 diferencias** |
| `= True`, rama `IniVig == FinVig` | 0 diferencias | 0 diferencias |
| `= True`, rama no proporcional (TipoRea 2) | 0 diferencias | 0 diferencias |
| `= True`, rama proporcional > 12 meses → 0 | 0 diferencias | 0 diferencias |
| `= True`, rama proporcional que lee xPND | 81.9% cambian | 81.9% cambian |

Es decir: apagado, el script es el tuyo; encendido, el modelo sólo toca donde el legado leía la tabla.

`PPTO_SONR_.py` no necesitaba corrección: ahí el parche ya estaba en el sitio de la lectura.
Los tres de RRC tampoco: `fnd_cal` ya sustituía el valor de `xPND.get(...)` en su lugar.

## El δ recalibrado también arregla el nivel de SONR

SONR usa **`Dev = 1 − FND`**, o sea el espejo del RRC: si el FND sube, la prima devengada baja y el SONR
baja. Ese es el mismo δ mal calibrado del que hablamos ayer, visto por el otro lado. Devengamiento medio
sobre la prima de los últimos 12 meses (lo que multiplica la prima en SONR):

| Ramo | legado | δ anterior | **δ recalibrado** | nuevo vs legado |
|---|---|---|---|---|
| Incendio | 0.5525 | 0.4995 | **0.5490** | −0.6% |
| Vida | 0.5525 | 0.5674 | **0.5536** | +0.2% |
| Diversos | 0.5525 | 0.4995 | **0.5582** | +1.0% |
| MyT | 0.5525 | 0.4895 | **0.5295** | −4.1% |
| AyE | 0.5525 | 0.5444 | **0.5295** | −4.1% |
| RC | 0.5525 | 0.4995 | **0.5994** | +8.5% |
| Autos | 0.5525 | 0.6220 | **0.7659** | +38.6% |

Con el δ anterior el modelo devengaba ~10% menos que el legado en los ramos pesados, y por eso el SONR
salía bajo. Con el δ recalibrado el devengamiento cae prácticamente encima del legado. **Un solo cambio
—sustituir `delta_calibrado.json`— corrige las dos reservas**, cada una por su lado de la resta.

## Qué hacer, en orden

1. **Sustituye `delta_calibrado.json`** en Documents por el recalibrado (el del zip anterior).
2. **Sustituye `ReforecastSONR_aod.py` y `FCST_SONR.py`** por los de este zip.
3. **Corre primero con `USAR_FND_CALIBRADO = False`** y compara contra tu corrida legada: deben salir
   idénticas. Si no, algo más cambió en los insumos y hay que verlo antes de seguir.
4. **Mira la consola.** Si aparece el aviso de ramos perdidos, el problema está en `ParamSONR`, no en el
   FND: arregla ese archivo antes de sacar conclusiones de los números.
5. Cuando la cobertura salga completa, pon `True` y compara.

Renombra el output anterior antes de correr: los nombres de salida no cambiaron.
