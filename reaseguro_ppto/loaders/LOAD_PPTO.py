import pandas as pd

def cargar_ppto(
    archivo_ppto
):

    xCuenta = {
        "53": "Comisiones",
        "54": "Siniestros",
        "61": "Primas"
    }

    df = pd.read_csv(
        archivo_ppto,
        low_memory=False
    )

    df = df[
        df["0FISCYEAR"] < 2033
    ]

    df["/ERP/GL_ACCT"] = (
        df["/ERP/GL_ACCT"]
        .astype(str)
        .str[:2]
        .map(xCuenta)
    )

    return df