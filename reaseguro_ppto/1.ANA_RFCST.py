import pandas as pd
import time
import warnings
import getpass
import numpy as np
import os

# =====================================================
# CONFIGURACION
# =====================================================

warnings.filterwarnings('ignore')

inicio = time.perf_counter()

usuario = getpass.getuser()

xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Documentos\Planeación Financiera\Presupuestos\2027\4_Validacion"

xInputs = os.path.join(xFolder, "Inputs")
xOutputs = os.path.join(xFolder, "Outputs")

archivo = os.path.join(xInputs,"BD_RFCST.xlsx")

archivo_salida = os.path.join(xOutputs,"ANA_RFCST.xlsx")

# =====================================================
# CARGA
# =====================================================

df = pd.read_excel(archivo)

# =====================================================
# LIMPIEZA
# =====================================================

columnas_numericas = [
    "Primas 1226",
    "Siniestros 1226",
    "Costos 1226",
    "Primas PPTO1226",
    "Siniestros PPTO1226",
    "Costos PPTO1226",
    "Incr. Primas Hist",
    "Ind. Sin. Hist",
    "Ind. Cos. Hist",
    "Incr. Primas Ppto",
    "Ind. Sin. Ppto",
    "Ind. Cos. Ppto"
]

df.columns = (df.columns.astype(str).str.strip())

for col in columnas_numericas:
    df[col] = pd.to_numeric(
        df[col],
        errors="coerce"
    )


df["LLAVE"] = (
df["LN"].astype(str)
+ "-" +
df["Tipo Reaseguro"].astype(str)
+ "-" +
df["País"].astype(str)
+ "-" +
df["Corredor"].astype(str)
+ "-" +
df["Num Contrato"].astype(str)
+ "-" +
df["Año Susc."].astype(str)
)

niveles = {
"LN": ["LN"],
"LN_TR": ["LN", "Tipo Reaseguro"],
"LN_PAIS": ["LN", "País"],
"LN_TIPOREA": ["LN", "Tipo Rea"],
"LN_CORREDOR": ["LN", "Corredor"],
"LN_COMPANIA": ["LN", "Compañía"],
"LN_BINDER": ["LN", "Binder Ppto"],
"COMPANIA": ["Compañía"],
"CORREDOR": ["Corredor"],
"PAIS": ["País"],
"BINDER": ["Binder Ppto"],
"CONTRATO": ["Num Contrato"],
"LN_CONTRATO": ["LN", "Num Contrato"],
"LN_ANIO_SUSC": ["LN", "Año Susc."],
"LN_TR_CONTRATO": ["LN","Tipo Reaseguro","Num Contrato"],
"LN_TR_PAIS":["LN","Tipo Reaseguro","País"],
"LN_TR_CORREDOR": ["LN","Tipo Reaseguro","Corredor"],
"LN_TR_BINDER":["LN","Tipo Reaseguro","Binder Ppto"],
"LLAVE_COMPLETA": ["LN","Tipo Reaseguro","País","Tipo Rea","Binder Ppto","Corredor","Compañía","Num Contrato","Año Susc."]}

def valor_excel(x):
    if pd.isna(x):
        return 0
    if np.isinf(x):
        return 0
    return float(x)

# =====================================================
# SEMAFORO PRIMAS
# =====================================================

def semaforo_primas(x):

    if pd.isna(x):
        return "SIN DATO"

    if abs(x) > 0.20:
        return "ROJO"

    elif abs(x) > 0.10:
        return "AMARILLO"

    else:
        return "VERDE"

# =====================================================
# SEMAFORO SIN
# =====================================================

def semaforo_sin(x):

    if pd.isna(x):
        return "SIN DATO"

    if x > 1:
        return "ROJO"

    elif x > 0.80:
        return "AMARILLO"

    else:
        return "VERDE"

# =====================================================
# SEMAFORO COSTOS
# =====================================================

def semaforo_costos(x):

    if pd.isna(x):
        return "SIN DATO"

    if x > 0.50:
        return "ROJO"

    elif x > 0.35:
        return "AMARILLO"

    else:
        return "VERDE"


# =====================================================
# NIVEL RIESGO
# =====================================================

def nivel_riesgo(x):

    if x >= 80:
        return "CRITICO"

    elif x >= 60:
        return "ALTO"

    elif x >= 40:
        return "MEDIO"

    else:
        return "BAJO"



# =====================================================
# RESUMEN POR NIVELES
# =====================================================

def generar_resumen(df, group_cols):

    resumen = (
        df
        .groupby(group_cols)
        .agg({
            "Primas 1226":"sum",
            "Siniestros 1226":"sum",
            "Costos 1226":"sum",

            "Primas PPTO1226":"sum",
            "Siniestros PPTO1226":"sum",
            "Costos PPTO1226":"sum",

            "Incr. Primas Hist":"mean",
            "Ind. Sin. Hist":"mean",
            "Ind. Cos. Hist":"mean",

            "Incr. Primas Ppto":"mean",
            "Ind. Sin. Ppto":"mean",
            "Ind. Cos. Ppto":"mean"
        })
        .reset_index()
    )

# =====================================================
# KPI FORECAST
# =====================================================

    resumen["Ind. Sin. RFCST"] = np.where(
        resumen["Primas 1226"] != 0,
        resumen["Siniestros 1226"] / resumen["Primas 1226"],
        np.nan
    )

    resumen["Ind. Cos. RFCST"] = np.where(
        resumen["Primas 1226"] != 0,
        resumen["Costos 1226"] / resumen["Primas 1226"],
        np.nan
    )

# =====================================================
# DESVIACIONES VS PPTO
# =====================================================

    resumen["Var_Primas_PPTO"] = np.where(
        resumen["Primas PPTO1226"] != 0,
        resumen["Primas 1226"] / resumen["Primas PPTO1226"] - 1,
        np.nan
    )

    resumen["Var_Siniestros_PPTO"] = np.where(
        resumen["Siniestros PPTO1226"] != 0,
        resumen["Siniestros 1226"] / resumen["Siniestros PPTO1226"] - 1,
        np.nan
    )

    resumen["Var_Costos_PPTO"] = np.where(
        resumen["Costos PPTO1226"] != 0,
        resumen["Costos 1226"] /
        resumen["Costos PPTO1226"] - 1,
        np.nan
    )


# =====================================================
# GAPS
# =====================================================

    resumen["Gap_Primas"] = (
        resumen["Primas 1226"] -
        resumen["Primas PPTO1226"]
    )

    resumen["Gap_Siniestros"] = (
        resumen["Siniestros 1226"] -
        resumen["Siniestros PPTO1226"]
    )

    resumen["Gap_Costos"] = (
        resumen["Costos 1226"] -
        resumen["Costos PPTO1226"]
    )

    resumen["Gap_%_Primas"] = np.where(
        resumen["Primas PPTO1226"] != 0,
        resumen["Gap_Primas"] /
        resumen["Primas PPTO1226"],
        np.nan
    )

    resumen["Var_Ind_Sin"] = (
        resumen["Ind. Sin. RFCST"]
        - resumen["Ind. Sin. Ppto"]
    )

    resumen["Var_Ind_Cos"] = (
        resumen["Ind. Cos. RFCST"]
        - resumen["Ind. Cos. Ppto"]
    )

    resumen["Resultado_Tecnico"] = (
        resumen["Primas 1226"]
        - resumen["Siniestros 1226"]
        - resumen["Costos 1226"]
    )

    resumen["Margen_Tecnico"] = np.where(
        resumen["Primas 1226"] != 0,
        resumen["Resultado_Tecnico"] /
        resumen["Primas 1226"],
        np.nan
    )

# =====================================================
# CUMPLIMIENTO PPTO
# =====================================================

    resumen["Cumplimiento_Primas"] = np.where(
        resumen["Primas PPTO1226"] != 0,
        resumen["Primas 1226"] /
        resumen["Primas PPTO1226"],
        np.nan
    )

# =====================================================
# SEMÁFOROS
# =====================================================

    resumen["Semaforo_Primas"] = resumen[
        "Var_Primas_PPTO"
    ].apply(semaforo_primas)

    resumen["Semaforo_Sin"] = resumen[
        "Ind. Sin. RFCST"
    ].apply(semaforo_sin)

    resumen["Semaforo_Costos"] = resumen[
        "Ind. Cos. RFCST"
    ].apply(semaforo_costos)


# =====================================================
# SCORE RIESGO
# =====================================================

    resumen["Score_Primas"] = (
        np.minimum(
            np.abs(
                resumen["Var_Primas_PPTO"]
            ) * 100,
            100
        )
    )

    resumen["Score_Sin"] = (
        np.minimum(
            resumen["Ind. Sin. RFCST"] * 100,
            100
        )
    )

    resumen["Score_Costos"] = (
        np.minimum(
            resumen["Ind. Cos. RFCST"] * 100,
            100
        )
    )

    resumen["Score_Total"] = (

        resumen["Score_Primas"] * 0.35
        + resumen["Score_Sin"] * 0.45
        + resumen["Score_Costos"] * 0.20

    )

# =====================================================
# NIVEL RIESGO
# =====================================================

    resumen["Nivel_Riesgo"] = (
        resumen["Score_Total"]
        .apply(nivel_riesgo)
    )

    resumen["Participacion_Prima"] = np.where(
    resumen["Primas 1226"].sum() != 0,
    resumen["Primas 1226"] /
    resumen["Primas 1226"].sum(),
    np.nan
    )

    resumen["Participacion_Gap"] = np.where(
    resumen["Gap_Primas"].abs().sum() != 0,
    resumen["Gap_Primas"].abs() /
    resumen["Gap_Primas"].abs().sum(),
    np.nan
    )

# =====================================================
# COMITÉ
# =====================================================

    resumen["Ranking_Prima"] = (
    resumen["Primas 1226"]
    .rank(
    ascending=False,
    method="dense"
    )
    )

    resumen["Ranking_Gap"] = (
    resumen["Gap_Primas"]
    .abs()
    .rank(
    ascending=False,
    method="dense"
    )
    )

    return resumen

reportes = {}

for nombre, campos in niveles.items():
    print(f"Procesando {nombre}")
    reportes[nombre] = generar_resumen(
    df,
    campos
)

resumen = reportes["LLAVE_COMPLETA"].copy()

# =====================================================
# RANKING
# =====================================================

ranking = (
    resumen
    .sort_values(
        "Score_Total",
        ascending=False
    )
    .reset_index(drop=True)
)

ranking["Ranking"] = (
    ranking.index + 1
)

ranking_gap = (
    resumen
    .sort_values(
        "Gap_Primas",
        ascending=False
    )
)

ranking_gap["Gap_Acumulado"] = (
    ranking_gap["Gap_Primas"]
    .cumsum()
)

ranking_gap["%Acumulado"] = (
    ranking_gap["Gap_Acumulado"]
    /
    ranking_gap["Gap_Primas"].sum()
)

# =====================================================
# EXCEPCIONES
# =====================================================

excepciones = ranking[
    (
        ranking["Semaforo_Primas"] == "ROJO"
    )
    |
    (
        ranking["Semaforo_Sin"] == "ROJO"
    )
    |
    (
        ranking["Semaforo_Costos"] == "ROJO"
    )
]

# =====================================================
# TOP RIESGO
# =====================================================

top_riesgo = ranking.head(10)

# =====================================================
# TOP DESVIACION PPTO
# =====================================================

top_desviacion = (
    ranking
    .sort_values(
        "Var_Primas_PPTO",
        key=abs,
        ascending=False
    )
    .head(10)
)

# =====================================================
# TOPS COMITE
# =====================================================

top_gap = (
    resumen
    .sort_values(
    "Gap_Primas",
    ascending=False
    )
    .head(10)
)

top_contratos = (
    reportes["CONTRATO"]
    .sort_values(
    "Primas 1226",
    ascending=False
    )
    .head(10)
)

top_corredores = (
    reportes["CORREDOR"]
    .sort_values(
    "Primas 1226",
    ascending=False
    )
    .head(10)
)

top_binders = (
    reportes["BINDER"]
    .sort_values(
    "Primas 1226",
    ascending=False
    )
    .head(10)
)

# =====================================================
# DASHBOARD
# =====================================================

dashboard = pd.DataFrame({

    "Indicador": [
        "Total LLAVE",
        "Prima Forecast",
        "Prima PPTO",
        "Gap Prima",
        "LLAVE Criticas",
        "LLAVE Alto Riesgo",
        "LLAVE Medio Riesgo",
        "LLAVE Bajo Riesgo",
        "Margen Técnico",
        "Siniestralidad",
        "Costo %",
        "Cumplimiento Prima",
        "% Prima Top10 Riesgo"
    ],

    "Valor": [
        len(resumen),
        resumen["Primas 1226"].sum(),
        resumen["Primas PPTO1226"].sum(),
        resumen["Gap_Primas"].sum(),

        len(resumen[resumen["Nivel_Riesgo"] == "CRITICO"]),
        len(resumen[resumen["Nivel_Riesgo"] == "ALTO"]),
        len(resumen[resumen["Nivel_Riesgo"] == "MEDIO"]),
        len(resumen[resumen["Nivel_Riesgo"] == "BAJO"]),

        resumen["Margen_Tecnico"].mean(),
        resumen["Ind. Sin. RFCST"].mean(),
        resumen["Ind. Cos. RFCST"].mean(),
        resumen["Cumplimiento_Primas"].mean(),

        top_riesgo["Primas 1226"].sum()
        /
        resumen["Primas 1226"].sum()
    ]
})

# ==================================================
# EXPORTACION
# ==================================================

os.makedirs(xOutputs, exist_ok=True)

reportes_formato = {
**reportes,
"Dashboard": dashboard,
"Ranking_LLAVE": ranking,
"Excepciones": excepciones,
"Top10_Riesgo": top_riesgo,
"Top10_Desv": top_desviacion,
"Pareto_Gap": ranking_gap,
"Resumen_Ejecutivo": pd.DataFrame()
}

with pd.ExcelWriter(
    archivo_salida,
    engine="xlsxwriter"
) as writer:
    
    for nombre, tabla in reportes.items():
        tabla.to_excel(
            writer,
            sheet_name=nombre[:31],
            index=False
        )

    dashboard.to_excel(
        writer,
        sheet_name="Dashboard",
        index=False
    )

    ranking.to_excel(
        writer,
        sheet_name="Ranking_LLAVE",
        index=False
    )

    excepciones.to_excel(
        writer,
        sheet_name="Excepciones",
        index=False
    )

    top_riesgo.to_excel(
        writer,
        sheet_name="Top10_Riesgo",
        index=False
    )

    top_desviacion.to_excel(
        writer,
        sheet_name="Top10_Desv",
        index=False
    )

    ranking_gap.to_excel(
        writer,
        sheet_name="Pareto_Gap",
        index=False
    )

    resumen_ws = writer.book.add_worksheet(
    "Resumen_Ejecutivo"
    )

    writer.sheets["Resumen_Ejecutivo"] = resumen_ws

    resumen_ws.write(0,0,"RESUMEN EJECUTIVO FORECAST 2027")

    resumen_ws.write(2,0,"Prima Forecast")
    resumen_ws.write(2,1,resumen["Primas 1226"].sum())

    resumen_ws.write(3,0,"Prima PPTO")
    resumen_ws.write(3,1,resumen["Primas PPTO1226"].sum())

    resumen_ws.write(4,0,"Gap Prima")
    resumen_ws.write(4,1,resumen["Gap_Primas"].sum())

    resumen_ws.write(5,0,"Margen Técnico")
    resumen_ws.write(5,1,valor_excel(resumen["Margen_Tecnico"].mean()))

    resumen_ws.write(6,0,"Cumplimiento")
    resumen_ws.write(6,1,valor_excel(resumen["Cumplimiento_Primas"].mean()))

    resumen_ws.write(9,0,"TOP 10 RIESGOS")
    resumen_ws.write(9,15,"TOP 10 GAPS")
    resumen_ws.write(29,0,"TOP CONTRATOS")
    resumen_ws.write(29,12,"TOP CORREDORES")
    resumen_ws.write(29,24,"TOP BINDERS")


    top_riesgo.to_excel(
    writer,
    sheet_name="Resumen_Ejecutivo",
    startrow=10,
    startcol=0,
    index=False
    )

    top_gap.to_excel(
    writer,
    sheet_name="Resumen_Ejecutivo",
    startrow=10,
    startcol=15,
    index=False
    )

    top_contratos.to_excel(
    writer,
    sheet_name="Resumen_Ejecutivo",
    startrow=30,
    startcol=0,
    index=False
    )

    top_corredores.to_excel(
    writer,
    sheet_name="Resumen_Ejecutivo",
    startrow=30,
    startcol=12,
    index=False
    )

    top_binders.to_excel(
    writer,
    sheet_name="Resumen_Ejecutivo",
    startrow=30,
    startcol=24,
    index=False
    )


    # Ajustar ancho de columnas
    workbook = writer.book

    formato_rojo = workbook.add_format({
        "bg_color":"#FFC7CE"
    })

    formato_verde = workbook.add_format({
        "bg_color":"#C6EFCE"
    })

    formato_amarillo = workbook.add_format({
    "bg_color": "#FFEB9C"
    })

    formato_pct = workbook.add_format({
    "num_format": "0.0%"
    })

    for sheet_name, df_export in reportes_formato.items():
   
            worksheet = writer.sheets[sheet_name]

            if len(df_export.columns) > 0:
                worksheet.freeze_panes(1, 0)
                worksheet.autofilter(0,0,len(df_export),len(df_export.columns)-1)

           
            for col_num, col_name in enumerate(df_export.columns):

                    if col_name.startswith("Semaforo"):

                        worksheet.conditional_format(
                            1,
                            col_num,
                            len(df_export),
                            col_num,
                            {
                                "type": "text",
                                "criteria": "containing",
                                "value": "ROJO",
                                "format": formato_rojo
                            }
                        )

                        worksheet.conditional_format(
                            1,
                            col_num,
                            len(df_export),
                            col_num,
                            {
                                "type": "text",
                                "criteria": "containing",
                                "value": "AMARILLO",
                                "format": formato_amarillo
                            }
                        )

                        worksheet.conditional_format(
                            1,
                            col_num,
                            len(df_export),
                            col_num,
                            {
                                "type": "text",
                                "criteria": "containing",
                                "value": "VERDE",
                                "format": formato_verde
                            }
                        )
# Ajuste de ancho
            for col_num, col_name in enumerate(df_export.columns):

                ancho = max(
                    len(str(col_name)),
                    df_export[col_name].astype(str).str.len().max()
                    if len(df_export) > 0 else 0
                ) + 2

                if col_name in [
                    "Ind. Sin. RFCST",
                    "Ind. Cos. RFCST",
                    "Margen_Tecnico",
                    "Cumplimiento_Primas",
                    "Gap_%_Primas",
                    "Participacion_Prima",
                    "Participacion_Gap",
                    "Var_Primas_PPTO",
                    "Var_Siniestros_PPTO",
                    "Var_Costos_PPTO"
                ]:

                    worksheet.set_column(
                        col_num,
                        col_num,
                        max(ancho, 12),
                        formato_pct
                    )

                else:

                    worksheet.set_column(
                        col_num,
                        col_num,
                        min(ancho, 40)
                    )

fin = time.perf_counter()
print("=" * 60)
print("REPORTE GENERADO")
print("=" * 60)
print(archivo_salida)
print(f"Tiempo: {fin - inicio:.2f} segundos")
print("=" * 60)