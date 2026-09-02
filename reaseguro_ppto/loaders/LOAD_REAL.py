import pandas as pd

def cargar_real(archivo):

    df = pd.read_excel(archivo)

    return df