import pandas as pd

def crear_llave(df, columnas):

    return (
        df[columnas]
        .fillna(0)
        .astype(str)
        .agg("-".join, axis=1)
    )