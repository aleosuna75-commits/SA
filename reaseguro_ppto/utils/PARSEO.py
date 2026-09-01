"""Conversion de importes de texto a numero.

El archivo PptoTecnico viene de SAP con los importes como TEXTO y con
separador de miles: "-7,000.00", "-1,263,571,656,386.06".

pd.to_numeric(..., errors="coerce") NO entiende el separador de miles:
convierte a NaN todo importe de 1,000 en adelante y solo sobreviven los
menores a 1,000. Al sumar, los NaN valen 0 y el presupuesto queda
reducido a una fraccion diminuta del real.
"""

import pandas as pd


def a_numerico(serie, nombre="importe", tolerancia_nulos=0.0):
    """Convierte una serie de importes en texto a float.

    Maneja separador de miles ("1,234.56"), notacion contable con
    parentesis ("(1,234.56)") y signo al final ("1,234.56-").

    Lanza excepcion si algun valor no vacio no se pudo convertir, para que
    un cambio de formato en el origen no vuelva a pasar inadvertido.
    """

    if pd.api.types.is_numeric_dtype(serie):
        return serie.astype("float64")

    texto = (
        serie
        .astype("string")
        .str.strip()
        .str.replace(" ", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(",", "", regex=False)
    )

    # (1234.56) -> -1234.56
    negativo_parentesis = (
        texto.str.startswith("(", na=False)
        & texto.str.endswith(")", na=False)
    )
    texto = texto.str.strip("()")

    # 1234.56- -> -1234.56
    signo_al_final = texto.str.endswith("-", na=False)
    texto = texto.mask(
        signo_al_final,
        "-" + texto.str.rstrip("-")
    )

    numero = pd.to_numeric(texto, errors="coerce")
    numero = numero.mask(negativo_parentesis, -numero)

    vacio = texto.isna() | (texto == "")
    fallidos = numero.isna() & ~vacio

    if fallidos.any():
        n = int(fallidos.sum())
        pct = n / max(len(serie), 1)

        if pct > tolerancia_nulos:
            ejemplos = (
                serie[fallidos]
                .astype(str)
                .head(5)
                .tolist()
            )
            raise ValueError(
                f"No se pudieron convertir {n:,} valores de '{nombre}' "
                f"({pct:.2%} de las filas). Ejemplos: {ejemplos}"
            )

    return numero.fillna(0.0).astype("float64")


def validar_importes(df_original, serie_numerica, columna, etiqueta=""):
    """Compara el total del texto original contra el total convertido.

    Suma el texto crudo con una conversion independiente (str.replace)
    para detectar perdida de importes por parseo. El validador de pivotes
    existente NO detecta esto porque compara la columna ya convertida
    contra si misma.
    """

    crudo = pd.to_numeric(
        df_original[columna]
        .astype("string")
        .str.replace(",", "", regex=False)
        .str.strip(),
        errors="coerce"
    ).fillna(0.0)

    total_crudo = crudo.sum()
    total_convertido = serie_numerica.sum()
    diferencia = total_convertido - total_crudo

    print(f"\nVALIDACION DE PARSEO {etiqueta}")
    print(f"  Total texto crudo : {total_crudo:>24,.2f}")
    print(f"  Total convertido  : {total_convertido:>24,.2f}")
    print(f"  Diferencia        : {diferencia:>24,.2f}")

    if abs(diferencia) > 0.01:
        raise ValueError(
            f"Perdida de importes al convertir '{columna}': "
            f"crudo={total_crudo:,.2f} convertido={total_convertido:,.2f}"
        )

    print("  OK: no se perdieron importes al convertir")

    return total_convertido
