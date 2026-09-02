import numpy as np

def calcular_ratios(df):

    df["%Sin_r"] = np.where(
        df["Primas USD"] != 0,
        df["Siniestros USD"] / df["Primas USD"],
        0
    )

    df["%Com_r"] = np.where(
        df["Primas USD"] != 0,
        df["Comisiones USD"] / df["Primas USD"],
        0
    )

    df["%Sin_p"] = np.where(
        df["Primas"] != 0,
        df["Siniestros"] / df["Primas"],
        0
    )

    df["%Com_p"] = np.where(
        df["Primas"] != 0,
        df["Comisiones"] / df["Primas"],
        0
    )

    df["%Sin"] = np.where(
        df["PRIMAS_"] != 0,
        df["SINIESTROS_"] / df["PRIMAS_"],
        0
    )

    df["%Com"] = np.where(
        df["PRIMAS_"] != 0,
        df["COMISIONES_"] / df["PRIMAS_"],
        0
    )

    return df