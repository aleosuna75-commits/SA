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
