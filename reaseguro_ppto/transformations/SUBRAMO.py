"""Asignacion de Ramo al PPTO a partir del catalogo de Subramo.

MAIN.py carga el catalogo con `cargar_sbr(ARCHIVO_SUBRAMO)` y se lo pasa
a `procesar_contable` / `procesar_suscripcion` como tercer argumento.
El PPTO no trae Ramo propio: se lo tiene que traer de este catalogo para
poder cruzar contra el REAL, que si lo trae (`Ramo2`).

Este modulo NO adivina. Si no puede resolver con que columna cruzar o
cual es la columna de ramo del catalogo, deja el PPTO como estaba y lo
avisa en consola: es preferible que el proceso corra igual que antes a
que asigne un Ramo equivocado en silencio.
"""

import pandas as pd

# Posibles nombres de la columna de ramo dentro del catalogo.
CANDIDATOS_RAMO = [
    "Ramo",
    "RAMO",
    "ramo",
    "Ramo2",
    "Cve_Ramo",
    "CVE_RAMO",
    "Clave_Ramo",
]


def _detectar_columna_ramo(sbr):

    for columna in CANDIDATOS_RAMO:
        if columna in sbr.columns:
            return columna

    return None


def _normalizar(serie):
    """Deja la llave como texto limpio para que el cruce no falle por tipo.

    El PPTO trae los codigos como texto ("34.0") y el catalogo puede
    traerlos como numero (34). Sin normalizar, el merge no cruza nada.
    """

    texto = (
        serie
        .astype("string")
        .str.strip()
    )

    # "34.0" -> "34" para que cruce contra un catalogo entero.
    return texto.str.replace(
        r"\.0$",
        "",
        regex=True
    )


def asignar_ramo(ppto, sbr, etiqueta=""):
    """Trae el Ramo del catalogo Subramo hacia el PPTO.

    Devuelve el mismo DataFrame `ppto` con la columna "Ramo" poblada.
    """

    print(f"\nASIGNACION DE RAMO {etiqueta}")

    if "Ramo" not in ppto.columns:
        ppto["Ramo"] = pd.NA

    if sbr is None or len(sbr) == 0:
        print(
            "  AVISO: catalogo Subramo vacio o no recibido. "
            "Se conserva el Ramo actual del PPTO."
        )
        return ppto

    columna_ramo = _detectar_columna_ramo(sbr)

    if columna_ramo is None:
        print(
            "  AVISO: no se encontro columna de ramo en el catalogo. "
            f"Columnas disponibles: {list(sbr.columns)}"
        )
        print("  Se conserva el Ramo actual del PPTO.")
        return ppto

    llaves = [
        c for c in sbr.columns
        if c != columna_ramo and c in ppto.columns
    ]

    if not llaves:
        print(
            "  AVISO: el catalogo no comparte ninguna columna con el PPTO, "
            "no hay por donde cruzar."
        )
        print(f"  Columnas del catalogo: {list(sbr.columns)}")
        print("  Se conserva el Ramo actual del PPTO.")
        return ppto

    print(f"  Cruzando por: {llaves}")
    print(f"  Columna de ramo del catalogo: '{columna_ramo}'")

    catalogo = sbr[llaves + [columna_ramo]].copy()

    # El catalogo debe tener una sola fila por llave; si no, el merge
    # duplicaria filas del PPTO y se inflarian los importes.
    duplicados = catalogo.duplicated(subset=llaves).sum()

    if duplicados:
        print(
            f"  AVISO: {duplicados:,} llaves duplicadas en el catalogo. "
            "Se conserva la primera ocurrencia."
        )
        catalogo = catalogo.drop_duplicates(subset=llaves, keep="first")

    izquierda = pd.DataFrame(index=ppto.index)
    derecha = pd.DataFrame(index=catalogo.index)

    for llave in llaves:
        izquierda[llave] = _normalizar(ppto[llave])
        derecha[llave] = _normalizar(catalogo[llave])

    derecha["_RAMO_SBR_"] = catalogo[columna_ramo].astype("string").str.strip()

    filas_antes = len(ppto)

    cruce = izquierda.merge(
        derecha,
        how="left",
        on=llaves
    )

    if len(cruce) != filas_antes:
        raise ValueError(
            f"El cruce con Subramo cambio el numero de filas del PPTO: "
            f"{filas_antes:,} -> {len(cruce):,}. Revisar duplicados en "
            f"el catalogo sobre {llaves}."
        )

    ramo_nuevo = cruce["_RAMO_SBR_"].to_numpy()
    encontrados = pd.notna(ramo_nuevo)
    cobertura = encontrados.sum() / max(filas_antes, 1)

    # Solo se pisa el Ramo donde el catalogo si encontro correspondencia.
    ppto["Ramo"] = pd.Series(ramo_nuevo, index=ppto.index).fillna(ppto["Ramo"])

    print(
        f"  Cobertura: {encontrados.sum():,} de {filas_antes:,} filas "
        f"({cobertura:.1%})"
    )

    if cobertura == 0:
        print(
            "  AVISO: ninguna fila del PPTO cruzo contra el catalogo. "
            "Revisar que las llaves sean las correctas."
        )

    ppto["Ramo"] = ppto["Ramo"].fillna("SIN_VALOR").astype(str)

    print(f"  Ramos distintos en el PPTO: {ppto['Ramo'].nunique():,}")

    return ppto
