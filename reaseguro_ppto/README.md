# Por que las primas del PPTO salen tan bajas

## Causa

En `CONTABLE.py` y `SUSCRIPCION.py`:

```python
ppto["/ERP/AMOUNT"] = pd.to_numeric(
    ppto["/ERP/AMOUNT"],
    errors="coerce"
)
```

`PptoTecnico2026.csv` trae los importes **como texto y con separador de
miles**:

```
/ERP/AMOUNT
"-7,000.00"
"-100,000.00"
"-1,263,571,656,386.06"
```

`pd.to_numeric` no entiende la coma de miles. Con `errors="coerce"`
convierte a `NaN` **todo importe de 1,000 en adelante** y solo sobreviven
los menores a 1,000. Al sumar, los `NaN` cuentan como 0.

Sobre la base real (1,726,046 filas):

| | filas | % |
|---|---:|---:|
| Con coma -> `NaN` (se pierden) | 128,584 | 7.4% |
| Sin coma (sobreviven) | 1,597,462 | 92.6% |

Ese 7.4% de filas concentra practicamente el 100% del importe.

## Efecto en el output

| Concepto | Output actual | Correcto | Factor |
|---|---:|---:|---:|
| Primas | -8,034,183.15 | -1,979,283,365,798.06 | 246,358x |
| Siniestros | 5,758,331.59 | 1,006,742,469,979.97 | 174,832x |
| Comisiones | 10,386,602.23 | 794,682,454,366.00 | 76,510x |

Coincide con `CONTROL_TOTALES` de `Consulta_RP_C.xlsx`
(Primas PPTO = -8,650,480.10 contra REAL = 5,021,045,000, `%VAR` = -58,143%).
El PPTO no esta mal calculado: esta **mal leido**.

## Por que el validador no lo detecto

El validador compara la suma de la base contra la suma del pivote, pero
**ambas se calculan sobre la misma columna ya convertida**:

```python
primas_base  = ppto.loc[ppto["/ERP/GL_ACCT"] == "Primas", "/ERP/AMOUNT"].sum()
primas_pivot = df_ppto["Primas"].sum()
```

Si el parseo destruye los importes antes, los dos lados quedan igual de
mal y la validacion pasa. Valida el `pivot_table`, no la lectura.

## Correccion

`utils/PARSEO.py` agrega:

- `a_numerico(serie, nombre)` — quita el separador de miles y maneja
  notacion contable `(1,234.56)` y signo al final `1,234.56-`. Lanza
  excepcion si un valor no vacio no se puede convertir, para que un
  cambio de formato en el origen no vuelva a pasar inadvertido.
- `validar_importes(...)` — compara el total del texto crudo contra el
  total convertido. Es el validador que si detecta esta falla.

`CONTABLE.py` y `SUSCRIPCION.py` ya usan ambas.

### Mejor aun: corregirlo en el loader

Lo ideal es que el importe nunca entre como texto. En
`loaders/LOAD_PPTO.py`:

```python
ppto = pd.read_csv(
    ruta,
    thousands=",",       # <- clave
    decimal=".",
    encoding="utf-8-sig",
    low_memory=False
)
```

Con `thousands=","` pandas convierte bien desde la lectura. La
correccion de `utils/PARSEO.py` se queda como red de seguridad.

## Dos cosas mas que conviene revisar

1. **49 filas con importes >= 1,000 millones** (hasta
   -3,056,470,329,298.52 MXN en `LN04008-Agro` / 2034). Una vez corregido
   el parseo dominan el total. Excluyendolas, Primas queda en
   -3,228,896,691.17 MXN, que es un orden de magnitud razonable. Vale la
   pena validarlas en el origen antes de publicar cifras.

2. **Mezcla de monedas.** El PPTO esta 100% en MXN y el REAL en USD, pero
   `CONTABLE.py` los suma directo:

   ```python
   df["PRIMAS_"] = df["Primas"] + df["Primas USD"]
   ```

   Falta convertir a una moneda comun antes de sumar.

## Uso

```
python DIAGNOSTICO_PRIMAS.py "ruta\PptoTecnico2026.csv"
```

Imprime cuantas filas se pierden con la conversion actual y compara los
totales contra la corregida.

---

# Ajuste: `procesar_contable() takes 2 positional arguments but 3 were given`

## Causa

`MAIN.py` agrego la carga del catalogo de Subramo y lo pasa como tercer
argumento:

```python
sbr = cargar_sbr(ARCHIVO_SUBRAMO)
tablas_cont, nombres_cont = procesar_contable(ppto, real, sbr)
```

pero `procesar_contable` y `procesar_suscripcion` seguian declaradas con
dos parametros.

## Correccion

Ambas firmas ahora son:

```python
def procesar_contable(ppto, real, sbr=None):
def procesar_suscripcion(ppto, real, sbr=None):
```

`sbr=None` mantiene compatibilidad: si alguien las llama con dos
argumentos siguen funcionando.

El tercer argumento no se ignora. El PPTO **no trae Ramo propio** (el
REAL si, en `Ramo2`), y sin el las dos bases no cruzan por ramo. El nuevo
`transformations/SUBRAMO.py` lo asigna con `asignar_ramo(ppto, sbr)`,
que se llama antes de armar `LLAVE_`.

## Que hace `asignar_ramo`

- Detecta la columna de ramo del catalogo (`Ramo`, `RAMO`, `Cve_Ramo`...).
- Cruza por las columnas que el catalogo comparte con el PPTO.
- Normaliza las llaves a texto (`"34.0"` -> `"34"`), porque el PPTO trae
  los codigos como texto y el catalogo puede traerlos como numero. Sin
  esto el merge no cruza nada.
- Quita llaves duplicadas del catalogo y verifica que el numero de filas
  del PPTO no cambie, para no inflar importes.
- Imprime la **cobertura** del cruce (cuantas filas encontraron ramo).

**No adivina.** Si no puede resolver la llave o la columna de ramo, deja
el PPTO como estaba y lo avisa en consola, en lugar de asignar un Ramo
equivocado en silencio.

## Revisar la cobertura

Al correr, `MAIN.py` ahora imprime:

```
ASIGNACION DE RAMO (CONTABLE)
  Cruzando por: ['Contrato']
  Columna de ramo del catalogo: 'Ramo'
  Cobertura: 58,079 de 187,590 filas (31.0%)
```

Si la cobertura sale baja o en 0%, la llave detectada no es la correcta y
hay que fijarla a mano en `SUBRAMO.py`.

---

# Ajuste: `ModuleNotFoundError: No module named 'docx'`

## Causa

Dos cosas, y la segunda es la que importa.

**1. Falta la libreria.** `reports/REPORTE_WORD.py` usa `python-docx`, que
no esta instalada en el venv.

**2. El proceso completo se cae por una funcion que no se usa.**
`MAIN.py` importaba el reporte Word en la linea 14:

```python
from reports.REPORTE_WORD import generar_reporte_word
```

pero **todo el bloque que lo llama esta comentado** (lineas 114-125). O
sea: el import se ejecutaba siempre, tumbaba el proceso antes de leer un
solo registro, y ni siquiera para generar el Word — solo para importarlo.

## Correccion

### La libreria

Con el venv activado:

```
pip install python-docx
```

**OJO:** el paquete se llama `python-docx`, no `docx`. `pip install docx`
instala otra libreria distinta y abandonada, y el import sigue fallando.

Se agrego `requirements.txt` para no tener que acordarse:

```
pip install -r requirements.txt
```

### El import

Ahora el reporte Word se importa protegido. Si falta la libreria, avisa y
el proceso sigue: el Excel es lo obligatorio, el Word es opcional.

```python
try:
    from reports.REPORTE_WORD import generar_reporte_word
    REPORTE_WORD_DISPONIBLE = True

except ModuleNotFoundError:
    REPORTE_WORD_DISPONIBLE = False
    generar_reporte_word = None
    print("AVISO: python-docx no esta instalado, se omite el reporte Word.")
```

Probado en los dos escenarios: con la libreria instalada y sin ella.

## Ademas: un error que les iba a salir al descomentar el Word

El bloque comentado define `resumen_ln` pero llama con `tabla_ln`, que no
existe en ningun lado:

```python
#resumen_ln = next(...)          # <- define resumen_ln
#generar_reporte_word(
#    resumen_ln=tabla_ln,        # <- pero pasa tabla_ln  -> NameError
```

Ya quedo corregido a `resumen_ln=resumen_ln` dentro del comentario, y se
le agrego una verificacion de `REPORTE_WORD_DISPONIBLE` antes de llamarlo.

`generar_reporte_word` se probo por separado contra un `CONT_LN` con la
forma real y genera el .docx correctamente (portada, resumen, tabla de
KPIs y analisis por LN), incluyendo el caso de una LN con primas en cero.
