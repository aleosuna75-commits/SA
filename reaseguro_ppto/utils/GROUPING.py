def generar_resumen(
        df,
        group_cols,
        sort_cols,
        pct_group):

    medidas = [
        'Primas USD',
        'Siniestros USD',
        'Comisiones USD',
        'Primas',
        'Siniestros',
        'Comisiones',
        'PRIMAS_',
        'SINIESTROS_',
        'COMISIONES_'
    ]

    resultado = (
        df
        .groupby(group_cols)[medidas]
        .sum()
        .reset_index()
    )

    resultado.sort_values(
        sort_cols,
        inplace=True
    )

    resultado["%Inc_sin"] = (
        resultado
        .groupby(pct_group)
        ["SINIESTROS_"]
        .pct_change()
    )

    resultado["%Inc_com"] = (
        resultado
        .groupby(pct_group)
        ["COMISIONES_"]
        .pct_change()
    )

    resultado["%Prima"] = (
        resultado
        .groupby(pct_group)
        ["PRIMAS_"]
        .pct_change()
    )

    return resultado