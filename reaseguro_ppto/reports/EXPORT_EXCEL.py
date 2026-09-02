import pandas as pd

def exportar_excel(
    tablas,
    nombres,
    archivo
):

    with pd.ExcelWriter(
        archivo,
        engine="xlsxwriter"
    ) as writer:

        control = []

        for df, nombre in zip(
            tablas,
            nombres
        ):

            df.to_excel(
                writer,
                sheet_name=nombre,
                index=False
            )

            control.append(
                {
                    "Hoja": nombre,
                    "Registros": len(df),
                    "Columnas": len(df.columns)
                }
                )

        df_control = pd.DataFrame(control)

        df_control.to_excel(
            writer,
            sheet_name="CONTROL",
            index=False
        )
