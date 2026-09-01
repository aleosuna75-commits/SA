import pandas as pd
from utils.GROUPING import generar_resumen
from transformations.LLAVES import crear_llave
from utils.PARSEO import a_numerico, validar_importes

def procesar_contable(
    ppto,
    real
):
    tablas = []
    nombres = []

    # El origen SAP trae los importes como texto con separador de miles
    # ("-7,000.00"). pd.to_numeric los convertia en NaN y el presupuesto
    # quedaba reducido a las filas menores a 1,000.
    importes = a_numerico(
        ppto["/ERP/AMOUNT"],
        "/ERP/AMOUNT"
    )

    validar_importes(
        ppto,
        importes,
        "/ERP/AMOUNT",
        "(PPTO CONTABLE)"
    )

    ppto["/ERP/AMOUNT"] = importes

    #Homologacion de nombre ppto y real
    ppto["Linea_negocio"] = ppto["/ERP/FUNCAREA"]
    ppto["Region"] = ppto["ZREGIONRP"]
    ppto["Tipo_Reaseguro"] = ppto["ZTIPOREAS"]
    ppto["Cedente"] = ppto["ZCEDENTE"]
    ppto["Corredor"] = ppto["ZCORREDOR"]
    ppto["Contrato"] = ppto["ZCONTRATO"]
    ppto["AÑO_CONT"] = ppto["0CALYEAR"]

    real["Linea_negocio"] = real["LN"]
    real["Ramo"] = real["Ramo2"]
    real["Region"] = real["Terr2"]
    real["Tipo_Reaseguro"] = real["Tipo Rea"]
    real["Cedente"] = real["Compañía"]
    real["Contrato"] = real["Num Contrato"]
    real["AÑO_CONT"] = real["aPOG_AñoPrd"]

    columnas_llave = [
        "Linea_negocio",
        "Ramo",
        "Region",
        "Tipo_Reaseguro",
        "Cedente",
        "Corredor",
        "Contrato",
        "AÑO_CONT"
    ]

    for col in columnas_llave:

        ppto[col] = (
            ppto[col]
            .fillna("SIN_VALOR")
            .astype(str)
        )

        real[col] = (
            real[col]
            .fillna("SIN_VALOR")
            .astype(str)
        )

    columnas_llave = [
        "Linea_negocio",
        "Ramo",
        "Region",
        "Tipo_Reaseguro",
        "Cedente",
        "Corredor",
        "Contrato",
        "AÑO_CONT"
    ]

    ppto["LLAVE_"] = crear_llave(
        ppto,
        columnas_llave
    )

    real["LLAVE_"] = crear_llave(
        real,
        columnas_llave
    )

    print(
        ppto
        .groupby("/ERP/GL_ACCT")["/ERP/AMOUNT"]
        .sum()
    )


    df_ppto = (
        ppto
        .pivot_table(
            index=[
                "LLAVE_",
                "Linea_negocio",
                "Ramo",
                "Region",
                "Tipo_Reaseguro",
                "Corredor",
                "Cedente",
                "Contrato",
                "AÑO_CONT"
            ],
            columns="/ERP/GL_ACCT",
            values="/ERP/AMOUNT",
            aggfunc="sum"
        )
        .fillna(0)
        .reset_index()
    )

    print(
        df_ppto[
            [
                "Primas",
                "Siniestros",
                "Comisiones"
            ]
        ].sum()
    )

    # ==================================================
    # VALIDACION PPTO
    # ==================================================

    primas_base = (
        ppto.loc[
            ppto["/ERP/GL_ACCT"] == "Primas",
            "/ERP/AMOUNT"
        ].sum()
    )

    siniestros_base = (
        ppto.loc[
            ppto["/ERP/GL_ACCT"] == "Siniestros",
            "/ERP/AMOUNT"
        ].sum()
    )

    comisiones_base = (
        ppto.loc[
            ppto["/ERP/GL_ACCT"] == "Comisiones",
            "/ERP/AMOUNT"
        ].sum()
    )

    primas_pivot = df_ppto["Primas"].sum()
    siniestros_pivot = df_ppto["Siniestros"].sum()
    comisiones_pivot = df_ppto["Comisiones"].sum()

    print("\nVALIDACION PPTO")

    print(
        f"Primas      Base:{primas_base:,.2f} "
        f"Pivot:{primas_pivot:,.2f}"
    )

    print(
        f"Siniestros  Base:{siniestros_base:,.2f} "
        f"Pivot:{siniestros_pivot:,.2f}"
    )

    print(
        f"Comisiones  Base:{comisiones_base:,.2f} "
        f"Pivot:{comisiones_pivot:,.2f}"
    )


    # ==================================================
    # VALIDACION AUTOMATICA
    # ==================================================

    tolerancia = 0.01

    if abs(primas_base - primas_pivot) > tolerancia:
        raise Exception(
            f"Error Primas: Base={primas_base:,.2f} "
            f"Pivot={primas_pivot:,.2f}"
        )

    if abs(siniestros_base - siniestros_pivot) > tolerancia:
        raise Exception(
            f"Error Siniestros: Base={siniestros_base:,.2f} "
            f"Pivot={siniestros_pivot:,.2f}"
        )

    if abs(comisiones_base - comisiones_pivot) > tolerancia:
        raise Exception(
            f"Error Comisiones: Base={comisiones_base:,.2f} "
            f"Pivot={comisiones_pivot:,.2f}"
        )

    print("✓ Validación PPTO OK")

    df_real = (
        real
        .groupby(
            [
                "LLAVE_",
                "Linea_negocio",
                "Ramo",
                "Region",
                "Tipo_Reaseguro",
                "Corredor",
                "Cedente",
                "Contrato",
                "AÑO_CONT"
            ]
        )[
            [
                "Primas USD",
                "Siniestros USD",
                "Comisiones USD"
            ]
        ]
        .sum()
        .reset_index()
    )
    
    # ==================================================
    # CONTROL DE TOTALES
    # ==================================================

    control_totales = pd.DataFrame({
        "Concepto": [
            "Primas",
            "Siniestros",
            "Comisiones"
        ],
        "PPTO": [
            df_ppto["Primas"].sum(),
            df_ppto["Siniestros"].sum(),
            df_ppto["Comisiones"].sum()
        ],
        "REAL": [
            df_real["Primas USD"].sum(),
            df_real["Siniestros USD"].sum(),
            df_real["Comisiones USD"].sum()
        ]
    })

    control_totales["DIFERENCIA"] = (
        control_totales["REAL"]
        - control_totales["PPTO"]
    )

    control_totales["%VAR"] = (
        control_totales["DIFERENCIA"]
        /
        control_totales["PPTO"].replace(0, pd.NA)
    )

    control_totales["%VAR"] = (
        control_totales["%VAR"] * 100
    ).round(2)


    print("\nCONTROL TOTALES")
    print(
        control_totales.to_string(
            index=False
        )
    )
            

    df = df_ppto.merge(
        df_real,
        how="outer",
        on=[
            "LLAVE_",
            "Linea_negocio",
            "Ramo",
            "Region",
            "Tipo_Reaseguro",
            "Corredor",
            "Cedente",
            "Contrato",
            "AÑO_CONT"
        ]
    )

    df["Primas"] = df["Primas"].fillna(0)
    df["Siniestros"] = df["Siniestros"].fillna(0)
    df["Comisiones"] = df["Comisiones"].fillna(0)

    df["Primas USD"] = df["Primas USD"].fillna(0)
    df["Siniestros USD"] = df["Siniestros USD"].fillna(0)
    df["Comisiones USD"] = df["Comisiones USD"].fillna(0)

    df["PRIMAS_"] = (
        df["Primas"]
        + df["Primas USD"]
    )

    df["SINIESTROS_"] = (
        df["Siniestros"]
        + df["Siniestros USD"]
    )

    df["COMISIONES_"] = (
        df["Comisiones"]
        + df["Comisiones USD"]
    )
    
    #print("\nDF_PPTO")
    #print(df_ppto.columns.tolist())

    #print("\nDF_REAL")
    #print(df_real.columns.tolist())

    #print("\nDF_FINAL")
    #print(df.columns.tolist())

    niveles_cont = [

        {
            "nombre":"CONT_COMP",
            "group":[
                "AÑO_CONT"
            ],
            "sort":[
                "AÑO_CONT"
            ],
            "pct":"AÑO_CONT"
        },

        {
            "nombre":"CONT_LN",
            "group":[
                "Linea_negocio",
                "AÑO_CONT"
            ],
            "sort":[
                "Linea_negocio",
                "AÑO_CONT"
            ],
            "pct":"Linea_negocio"
        },

        {
            "nombre":"CONT_RAMO",
            "group":[
                "Ramo",
                "AÑO_CONT"
            ],
            "sort":[
                "Ramo",
                "AÑO_CONT"
            ],
            "pct":"Ramo"
        },

        {
            "nombre":"CONT_REGION",
            "group":[
                "Region",
                "AÑO_CONT"
            ],
            "sort":[
                "Region",
                "AÑO_CONT"
            ],
            "pct":"Region"
        },

        {
            "nombre":"CONT_TR",
            "group":[
                "Tipo_Reaseguro",
                "AÑO_CONT"
            ],
            "sort":[
                "Tipo_Reaseguro",
                "AÑO_CONT"
            ],
            "pct":"Tipo_Reaseguro"
        },

        {
            "nombre":"CONT_CEDENTE",
            "group":[
                "Cedente",
                "AÑO_CONT"
            ],
            "sort":[
                "Cedente",
                "AÑO_CONT"
            ],
            "pct":"Cedente"
        },

        {
            "nombre":"CONT_CORREDOR",
            "group":[
                "Corredor",
                "AÑO_CONT"
            ],
            "sort":[
                "Corredor",
                "AÑO_CONT"
            ],
            "pct":"Corredor"
        },

        {
            "nombre":"CONT_LLAVE",
            "group":[
                "LLAVE_",
                "AÑO_CONT"
            ],
            "sort":[
                "LLAVE_",
                "AÑO_CONT"
            ],
            "pct":"LLAVE_"
        }

    ]

    for nivel in niveles_cont:

        tabla = generar_resumen(
            df,
            nivel["group"],
            nivel["sort"],
            nivel["pct"]
        )

        tablas.append(tabla)

        nombres.append(
            nivel["nombre"]
        )

    tablas.insert(
        0,
        control_totales
    )

    nombres.insert(
        0,
        "CONTROL_TOTALES"
    )


    print("=" * 60)
    print("CONTABLE OK")
    print(f"Tablas generadas: {len(tablas)}")
    print("=" * 60)

    for nombre, tabla in zip(nombres, tablas):

        print(
            nombre,
            tabla.shape
        )




    return tablas, nombres