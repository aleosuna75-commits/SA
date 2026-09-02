import pandas as pd
import itertools
import xlwings as xw
import time
import numpy as np
import getpass
usuario = getpass.getuser()

xCuenta = {"53":'Comisiones',
            "54":'Siniestros',
            "61":'Primas'}

xFolder = fr"C:\Users\mocamachol\OneDrive - GPV\Planeación Financiera RPAT - Documents\Presupuestos\2026\3_Validacion\BD_PptoTécnico_2026"
xFile = fr"{xFolder}\PptoTécnico2026_Completo_SinGS.csv"
ConsultaPPTO = pd.read_csv(xFile, thousands=',')
ConsultaPPTO = ConsultaPPTO[(ConsultaPPTO["0FISCYEAR"] < 2033)]

xSubramo = pd.read_csv(f"{xFolder}\\Subramo.csv")
ConsultaPPTO= ConsultaPPTO.merge(xSubramo[["CeBe","Ramo"]].drop_duplicates(),
                             how="left", left_on="/ERP/PROFTCTR", right_on="CeBe")

ConsultaPPTO['/ERP/GL_ACCT'] = ConsultaPPTO['/ERP/GL_ACCT'].astype(str)
ConsultaPPTO['/ERP/GL_ACCT'] = ConsultaPPTO['/ERP/GL_ACCT'].str[:2]
ConsultaPPTO['/ERP/GL_ACCT'] =  ConsultaPPTO.apply(lambda row: xCuenta[row['/ERP/GL_ACCT']],axis=1)

Columnas = [ '/ERP/GL_ACCT', 'ZSUSCYEAR', 'ZTIPOREAS', 'ZREGIONRP', '0FISCYEAR', 'Ramo', '/ERP/FUNCAREA', '/ERP/AMOUNT']
ConsultaPPTO = ConsultaPPTO[Columnas]

ConsultaPPTO = ConsultaPPTO.pivot_table(index=['ZSUSCYEAR', 'ZTIPOREAS', 'ZREGIONRP', '0FISCYEAR', 'Ramo', '/ERP/FUNCAREA'], columns='/ERP/GL_ACCT', values='/ERP/AMOUNT', aggfunc='sum').reset_index()

ConsultaPPTO = ConsultaPPTO.groupby(['ZSUSCYEAR', 'ZTIPOREAS', 'ZREGIONRP', '0FISCYEAR', 'Ramo', '/ERP/FUNCAREA'])[['Comisiones', 'Siniestros', 'Primas']].sum().reset_index()
ConsultaPPTO['LLAVE'] = ConsultaPPTO[['/ERP/FUNCAREA', 'ZTIPOREAS', 'Ramo', 'ZREGIONRP']].apply(
    lambda x: '-'.join([
        str(x['/ERP/FUNCAREA'] if pd.notna(x['/ERP/FUNCAREA']) else 0), 
        str(int(x['ZTIPOREAS']) if pd.notna(x['ZTIPOREAS']) else 0), 
        str(int(x['Ramo']) if pd.notna(x['Ramo']) else 0),  
        str(x['ZREGIONRP'] if pd.notna(x['ZREGIONRP']) else 0) 
    ]), axis=1)

ConsultaPPTO['LLAVE2'] = ConsultaPPTO[['/ERP/FUNCAREA', 'ZTIPOREAS', 'Ramo', 'ZREGIONRP', '0FISCYEAR']].apply(
    lambda x: '-'.join([
        str(x['/ERP/FUNCAREA'] if pd.notna(x['/ERP/FUNCAREA']) else 0), 
        str(int(x['ZTIPOREAS']) if pd.notna(x['ZTIPOREAS']) else 0), 
        str(int(x['Ramo']) if pd.notna(x['Ramo']) else 0),  
        str(x['ZREGIONRP'] if pd.notna(x['ZREGIONRP']) else 0), 
        str(int(x['0FISCYEAR']) if pd.notna(x['0FISCYEAR']) else 0)
    ]), axis=1)

ConsultaPPTO['LLAVE3'] = ConsultaPPTO[['/ERP/FUNCAREA', 'ZTIPOREAS', 'Ramo', 'ZREGIONRP', 'ZSUSCYEAR']].apply(
    lambda x: '-'.join([
        str(x['/ERP/FUNCAREA'] if pd.notna(x['/ERP/FUNCAREA']) else 0), 
        str(int(x['ZTIPOREAS']) if pd.notna(x['ZTIPOREAS']) else 0), 
        str(int(x['Ramo']) if pd.notna(x['Ramo']) else 0),  
        str(x['ZREGIONRP'] if pd.notna(x['ZREGIONRP']) else 0), 
        str(int(x['ZSUSCYEAR']) if pd.notna(x['ZSUSCYEAR']) else 0)
    ]), axis=1)


ConsultaPPTO['Primas'] = ConsultaPPTO.apply(lambda row: -1 * row['Primas'], axis=1)

xFolder = fr"C:\Users\mocamachol\OneDrive - GPV\Planeación Financiera RPAT - Documents\Presupuestos\2026\3_Validacion\BD_PptoTécnico_2026"
xFile = fr"{xFolder}\BD_Real.xlsx"
ConsultaReal = pd.read_excel(xFile, thousands=',')

Columnas = ['Año Susc.', 'Tipo Rea', 'Terr2', 'Periodo', 'Ramo', 'LN', 'Primas USD', 'Siniestros USD', 'Comisiones USD']
ConsultaReal = ConsultaReal[Columnas]

ConsultaReal['Periodo'] = ConsultaReal['Periodo'].astype(str)
ConsultaReal['Periodo'] = ConsultaReal['Periodo'].str[:4]

ConsultaReal = ConsultaReal.groupby(['Año Susc.', 'Tipo Rea', 'Terr2', 'Periodo', 'Ramo', 'LN'])[['Comisiones USD', 'Siniestros USD', 'Primas USD']].sum().reset_index()
ConsultaReal['LLAVE'] = ConsultaReal[['LN', 'Tipo Rea', 'Ramo', 'Terr2']].apply(
    lambda x: '-'.join([
        str(x['LN'] if pd.notna(x['LN']) else 0), 
        str(int(x['Tipo Rea']) if pd.notna(x['Tipo Rea']) else 0), 
        str(int(x['Ramo']) if pd.notna(x['Ramo']) else 0),  
        str(x['Terr2'] if pd.notna(x['Terr2']) else 0) 
    ]), axis=1)

ConsultaReal['LLAVE2'] = ConsultaReal[['LN', 'Tipo Rea', 'Ramo', 'Terr2', 'Periodo']].apply(
    lambda x: '-'.join([
        str(x['LN'] if pd.notna(x['LN']) else 0), 
        str(int(x['Tipo Rea']) if pd.notna(x['Tipo Rea']) else 0), 
        str(int(x['Ramo']) if pd.notna(x['Ramo']) else 0),  
        str(x['Terr2'] if pd.notna(x['Terr2']) else 0), 
        str(int(x['Periodo']) if pd.notna(x['Periodo']) else 0)
    ]), axis=1)

ConsultaReal['LLAVE3'] = ConsultaReal[['LN', 'Tipo Rea', 'Ramo', 'Terr2', 'Año Susc.']].apply(
    lambda x: '-'.join([
        str(x['LN'] if pd.notna(x['LN']) else 0), 
        str(int(x['Tipo Rea']) if pd.notna(x['Tipo Rea']) else 0), 
        str(int(x['Ramo']) if pd.notna(x['Ramo']) else 0),  
        str(x['Terr2'] if pd.notna(x['Terr2']) else 0), 
        str(int(x['Año Susc.']) if pd.notna(x['Año Susc.']) else 0)
    ]), axis=1)

Tablas_C = []
Tablas_S = []


ConsultaxLN_C = ConsultaPPTO.drop(columns=["ZSUSCYEAR"])
ConsultaxLN_S = ConsultaPPTO.drop(columns=["0FISCYEAR"])
ConsultaxLN_C = ConsultaxLN_C.groupby(["/ERP/FUNCAREA", "ZTIPOREAS", "Ramo", "ZREGIONRP", "0FISCYEAR", "LLAVE", "LLAVE2"]).agg({"Primas": "sum", "Siniestros": "sum", "Comisiones": "sum"}).reset_index()
ConsultaxLN_S = ConsultaxLN_S.groupby(["/ERP/FUNCAREA", "ZTIPOREAS", "Ramo", "ZREGIONRP", "ZSUSCYEAR", "LLAVE", "LLAVE3"]).agg({"Primas": "sum", "Siniestros": "sum", "Comisiones": "sum"}).reset_index()

ConsultaxLN_real_C = ConsultaReal.drop(columns=["Año Susc."])
ConsultaxLN_real_S = ConsultaReal.drop(columns=["Periodo"])
ConsultaxLN_real_C = ConsultaxLN_real_C.groupby(["LN", "Tipo Rea", "Ramo", "Terr2", "Periodo", "LLAVE", "LLAVE2"]).agg({"Primas USD": "sum", "Siniestros USD": "sum", "Comisiones USD": "sum"}).reset_index()
ConsultaxLN_real_S = ConsultaxLN_real_S.groupby(["LN", "Tipo Rea", "Ramo", "Terr2", "Año Susc.", "LLAVE", "LLAVE3"]).agg({"Primas USD": "sum", "Siniestros USD": "sum", "Comisiones USD": "sum"}).reset_index()
    
ConsultaP_R_C_xLN = ConsultaxLN_real_C.merge(ConsultaxLN_C.drop_duplicates(subset=["LLAVE2"]), how="outer", on="LLAVE2")
ConsultaP_R_S_xLN = ConsultaxLN_real_S.merge(ConsultaxLN_S.drop_duplicates(subset=["LLAVE3"]), how="right", on="LLAVE3")

######## Cont
ConsultaP_R_C_xLN['AÑO_CONT'] = ConsultaP_R_C_xLN['LLAVE2'].str[-4:].astype(int)
ConsultaP_R_C_xLN['Linea_neg'] = np.where(ConsultaP_R_C_xLN['LN'].notnull(), ConsultaP_R_C_xLN['LN'], ConsultaP_R_C_xLN['/ERP/FUNCAREA'])
ConsultaP_R_C_xLN['Ramo'] = np.where(ConsultaP_R_C_xLN['Ramo_x'].notnull(), ConsultaP_R_C_xLN['Ramo_x'], ConsultaP_R_C_xLN['Ramo_y'])
ConsultaP_R_C_xLN['TipoRea'] = np.where(ConsultaP_R_C_xLN['ZTIPOREAS'].notnull(), ConsultaP_R_C_xLN['ZTIPOREAS'], ConsultaP_R_C_xLN['Tipo Rea'])
ConsultaP_R_C_xLN['Terr'] = np.where(ConsultaP_R_C_xLN['ZREGIONRP'].notnull(), ConsultaP_R_C_xLN['ZREGIONRP'], ConsultaP_R_C_xLN['Terr2'])
ConsultaP_R_C_xLN['PRIMAS_'] = ConsultaP_R_C_xLN.apply(lambda row: row['Primas USD'] if row['AÑO_CONT'] < 2025 else row['Primas'], axis=1)
ConsultaP_R_C_xLN['SINIESTROS_'] = ConsultaP_R_C_xLN.apply(lambda row: row['Siniestros USD'] if row['AÑO_CONT'] < 2025 else row['Siniestros'], axis=1)
ConsultaP_R_C_xLN['COMISIONES_'] = ConsultaP_R_C_xLN.apply(lambda row: row['Comisiones USD'] if row['AÑO_CONT'] < 2025 else row['Comisiones'], axis=1)
ConsultaP_R_C_xLN['LLAVE_'] = ConsultaP_R_C_xLN.apply(lambda row: row['LLAVE_x'] if row['AÑO_CONT'] < 2025 else row['LLAVE_y'], axis=1)

ConsultaP_R_C_xLN['LLAVE_LN'] = ConsultaP_R_C_xLN[['Linea_neg', 'AÑO_CONT']].apply(
    lambda x: '-'.join([
        str(x['Linea_neg'] if pd.notna(x['Linea_neg']) else 0), 
        str(int(x['AÑO_CONT']) if pd.notna(x['AÑO_CONT']) else 0)
    ]), axis=1)

ConsultaP_R_C_xLN['LLAVE_LN_TR'] = ConsultaP_R_C_xLN[['Linea_neg', 'AÑO_CONT', 'TipoRea']].apply(
    lambda x: '-'.join([
        str(x['Linea_neg'] if pd.notna(x['Linea_neg']) else 0), 
        str(int(x['AÑO_CONT']) if pd.notna(x['AÑO_CONT']) else 0),
        str(int(x['TipoRea']) if pd.notna(x['TipoRea']) else 0)
    ]), axis=1)

ConsultaP_R_C_xLN['LLAVE_LN_R'] = ConsultaP_R_C_xLN[['Linea_neg', 'AÑO_CONT', 'Ramo']].apply(
    lambda x: '-'.join([
        str(x['Linea_neg'] if pd.notna(x['Linea_neg']) else 0), 
        str(int(x['AÑO_CONT']) if pd.notna(x['AÑO_CONT']) else 0),
        str(int(x['Ramo']) if pd.notna(x['Ramo']) else 0)
    ]), axis=1)

ConsultaP_R_C_xLN['LLAVE_LN_T'] = ConsultaP_R_C_xLN[['Linea_neg', 'AÑO_CONT', 'Terr']].apply(
    lambda x: '-'.join([
        str(x['Linea_neg'] if pd.notna(x['Linea_neg']) else 0), 
        str(int(x['AÑO_CONT']) if pd.notna(x['AÑO_CONT']) else 0),
        str(x['Terr'] if pd.notna(x['Terr']) else 0)
    ]), axis=1)

ConsultaP_R_C_xLN['LLAVE_LN_TR_R'] = ConsultaP_R_C_xLN[['Linea_neg', 'AÑO_CONT', 'TipoRea', 'Ramo']].apply(
    lambda x: '-'.join([
        str(x['Linea_neg'] if pd.notna(x['Linea_neg']) else 0), 
        str(int(x['AÑO_CONT']) if pd.notna(x['AÑO_CONT']) else 0),
        str(int(x['TipoRea']) if pd.notna(x['TipoRea']) else 0),
        str(int(x['Ramo']) if pd.notna(x['Ramo']) else 0)
    ]), axis=1)




#####GROUP BY X LLAVE
Consulta_Ori = ConsultaP_R_C_xLN.groupby(['LLAVE_', 'Linea_neg','AÑO_CONT'])[['Primas USD', 'Siniestros USD', 'Comisiones USD', 'Primas', 'Siniestros', 'Comisiones', 'PRIMAS_', 'SINIESTROS_', 'COMISIONES_']].sum().reset_index()
Consulta_Ori.sort_values(by=['LLAVE_', 'AÑO_CONT'], inplace=True)
Consulta_Ori['%Inc_sin'] = Consulta_Ori.groupby('Linea_neg')['SINIESTROS_'].pct_change()
Consulta_Ori['%Inc_com'] = Consulta_Ori.groupby('Linea_neg')['COMISIONES_'].pct_change()
Consulta_Ori['%Prima'] = Consulta_Ori.groupby('Linea_neg')['PRIMAS_'].pct_change()
Tablas_C.append(Consulta_Ori)

Consulta_1 = ConsultaP_R_C_xLN.groupby(['LLAVE_LN', 'Linea_neg', 'AÑO_CONT'])[['Primas USD', 'Siniestros USD', 'Comisiones USD', 'Primas', 'Siniestros', 'Comisiones', 'PRIMAS_', 'SINIESTROS_', 'COMISIONES_']].sum().reset_index()
Consulta_1.sort_values(by=['LLAVE_LN', 'AÑO_CONT'], inplace=True)
Consulta_1['%Inc_sin'] = Consulta_1.groupby('Linea_neg')['SINIESTROS_'].pct_change()
Consulta_1['%Inc_com'] = Consulta_1.groupby('Linea_neg')['COMISIONES_'].pct_change()
Consulta_1['%Prima'] = Consulta_1.groupby('Linea_neg')['PRIMAS_'].pct_change()
Tablas_C.append(Consulta_1)

Consulta_2 = ConsultaP_R_C_xLN.groupby(['LLAVE_LN_TR', 'Linea_neg', 'TipoRea', 'AÑO_CONT'])[['Primas USD', 'Siniestros USD', 'Comisiones USD', 'Primas', 'Siniestros', 'Comisiones', 'PRIMAS_', 'SINIESTROS_', 'COMISIONES_']].sum().reset_index()
Consulta_2.sort_values(by=['Linea_neg', 'TipoRea', 'AÑO_CONT'], inplace=True)
Consulta_2['%Inc_sin'] = Consulta_2.groupby('TipoRea')['SINIESTROS_'].pct_change()
Consulta_2['%Inc_com'] = Consulta_2.groupby('TipoRea')['COMISIONES_'].pct_change()
Consulta_2['%Prima'] = Consulta_2.groupby('TipoRea')['PRIMAS_'].pct_change()
Tablas_C.append(Consulta_2)

Consulta_3 = ConsultaP_R_C_xLN.groupby(['LLAVE_LN_R', 'Linea_neg', 'Ramo', 'AÑO_CONT'])[['Primas USD', 'Siniestros USD', 'Comisiones USD', 'Primas', 'Siniestros', 'Comisiones', 'PRIMAS_', 'SINIESTROS_', 'COMISIONES_']].sum().reset_index()
Consulta_3.sort_values(by=['Linea_neg', 'Ramo', 'AÑO_CONT'], inplace=True)
Consulta_3['%Inc_sin'] = Consulta_3.groupby('Ramo')['SINIESTROS_'].pct_change()
Consulta_3['%Inc_com'] = Consulta_3.groupby('Ramo')['COMISIONES_'].pct_change()
Consulta_3['%Prima'] = Consulta_3.groupby('Ramo')['PRIMAS_'].pct_change()
Tablas_C.append(Consulta_3)

Consulta_4 = ConsultaP_R_C_xLN.groupby(['LLAVE_LN_T', 'Linea_neg', 'Terr', 'AÑO_CONT'])[['Primas USD', 'Siniestros USD', 'Comisiones USD', 'Primas', 'Siniestros', 'Comisiones', 'PRIMAS_', 'SINIESTROS_', 'COMISIONES_']].sum().reset_index()
Consulta_4.sort_values(by=['Linea_neg', 'Terr', 'AÑO_CONT'], inplace=True)
Consulta_4['%Inc_sin'] = Consulta_4.groupby('Terr')['SINIESTROS_'].pct_change()
Consulta_4['%Inc_com'] = Consulta_4.groupby('Terr')['COMISIONES_'].pct_change()
Consulta_4['%Prima'] = Consulta_4.groupby('Terr')['PRIMAS_'].pct_change()
Tablas_C.append(Consulta_4)

Consulta_5 = ConsultaP_R_C_xLN.groupby(['LLAVE_LN_TR_R', 'Linea_neg', 'TipoRea', 'Ramo', 'AÑO_CONT'])[['Primas USD', 'Siniestros USD', 'Comisiones USD', 'Primas', 'Siniestros', 'Comisiones', 'PRIMAS_', 'SINIESTROS_', 'COMISIONES_']].sum().reset_index()
Consulta_5.sort_values(by=['Linea_neg', 'TipoRea', 'Ramo', 'AÑO_CONT'], inplace=True)
Consulta_5['%Inc_sin'] = Consulta_5.groupby('Ramo')['SINIESTROS_'].pct_change()
Consulta_5['%Inc_com'] = Consulta_5.groupby('Ramo')['COMISIONES_'].pct_change()
Consulta_5['%Prima'] = Consulta_5.groupby('Ramo')['PRIMAS_'].pct_change()
Tablas_C.append(Consulta_5)

for df in Tablas_C:
    # Cálculos de porcentajes
    df['%Sin_r'] = df.apply(lambda row: row['Siniestros USD'] / row['Primas USD'] if row['Primas USD'] != 0 else 0, axis=1)
    df['%Com_r'] = df.apply(lambda row: row['Comisiones USD'] / row['Primas USD'] if row['Primas USD'] != 0 else 0, axis=1)
    df['%Sin_p'] = df.apply(lambda row: row['Siniestros'] / row['Primas'] if row['Primas'] != 0 else 0, axis=1)
    df['%Com_p'] = df.apply(lambda row: row['Comisiones'] / row['Primas'] if row['Primas'] != 0 else 0, axis=1)
    df['%Sin'] = df.apply(lambda row: row['SINIESTROS_'] / row['PRIMAS_'] if row['PRIMAS_'] != 0 else 0, axis=1)
    df['%Com'] = df.apply(lambda row: row['COMISIONES_'] / row['PRIMAS_'] if row['PRIMAS_'] != 0 else 0, axis=1)

    


    
    
######## Susc
ConsultaP_R_S_xLN['PRIMAS_'] = ConsultaP_R_S_xLN.apply(lambda row: (0 if pd.isna(row['Primas USD']) else row['Primas USD']) + (0 if pd.isna(row['Primas']) else row['Primas']), axis=1)
ConsultaP_R_S_xLN['SINIESTROS_'] = ConsultaP_R_S_xLN.apply(lambda row: (0 if pd.isna(row['Siniestros USD']) else row['Siniestros USD']) + (0 if pd.isna(row['Siniestros']) else row['Siniestros']), axis=1)
ConsultaP_R_S_xLN['COMISIONES_'] = ConsultaP_R_S_xLN.apply(lambda row: (0 if pd.isna(row['Comisiones USD']) else row['Comisiones USD']) + (0 if pd.isna(row['Comisiones']) else row['Comisiones']), axis=1)
ConsultaP_R_S_xLN['LLAVE_'] = ConsultaP_R_S_xLN.apply(lambda row: row['LLAVE_y'], axis=1)
ConsultaP_R_S_xLN['AÑO_SUSC'] = ConsultaP_R_S_xLN.apply(lambda row: row['ZSUSCYEAR'], axis=1)

ConsultaP_R_S_xLN['LLAVE_LN'] = ConsultaP_R_S_xLN[['/ERP/FUNCAREA', 'AÑO_SUSC']].apply(
    lambda x: '-'.join([
        str(x['/ERP/FUNCAREA'] if pd.notna(x['/ERP/FUNCAREA']) else 0), 
        str(int(x['AÑO_SUSC']) if pd.notna(x['AÑO_SUSC']) else 0)
    ]), axis=1)

ConsultaP_R_S_xLN['LLAVE_LN_TR'] = ConsultaP_R_S_xLN[['/ERP/FUNCAREA', 'AÑO_SUSC', 'ZTIPOREAS']].apply(
    lambda x: '-'.join([
        str(x['/ERP/FUNCAREA'] if pd.notna(x['/ERP/FUNCAREA']) else 0), 
        str(int(x['AÑO_SUSC']) if pd.notna(x['AÑO_SUSC']) else 0),
        str(int(x['ZTIPOREAS']) if pd.notna(x['ZTIPOREAS']) else 0)
    ]), axis=1)

ConsultaP_R_S_xLN['LLAVE_LN_R'] = ConsultaP_R_S_xLN[['/ERP/FUNCAREA', 'AÑO_SUSC', 'Ramo_y']].apply(
    lambda x: '-'.join([
        str(x['/ERP/FUNCAREA'] if pd.notna(x['/ERP/FUNCAREA']) else 0), 
        str(int(x['AÑO_SUSC']) if pd.notna(x['AÑO_SUSC']) else 0),
        str(int(x['Ramo_y']) if pd.notna(x['Ramo_y']) else 0)
    ]), axis=1)

ConsultaP_R_S_xLN['LLAVE_LN_T'] = ConsultaP_R_S_xLN[['/ERP/FUNCAREA', 'AÑO_SUSC', 'ZREGIONRP']].apply(
    lambda x: '-'.join([
        str(x['/ERP/FUNCAREA'] if pd.notna(x['/ERP/FUNCAREA']) else 0), 
        str(int(x['AÑO_SUSC']) if pd.notna(x['AÑO_SUSC']) else 0),
        str(x['ZREGIONRP'] if pd.notna(x['ZREGIONRP']) else 0)
    ]), axis=1)

ConsultaP_R_S_xLN['LLAVE_LN_TR_R'] = ConsultaP_R_S_xLN[['/ERP/FUNCAREA', 'AÑO_SUSC', 'ZTIPOREAS', 'Ramo_y']].apply(
    lambda x: '-'.join([
        str(x['/ERP/FUNCAREA'] if pd.notna(x['/ERP/FUNCAREA']) else 0), 
        str(int(x['AÑO_SUSC']) if pd.notna(x['AÑO_SUSC']) else 0),
        str(int(x['ZTIPOREAS']) if pd.notna(x['ZTIPOREAS']) else 0),
        str(int(x['Ramo_y']) if pd.notna(x['Ramo_y']) else 0)
    ]), axis=1)


    #####GROUP BY X LLAVE
Consulta_Ori_ = ConsultaP_R_S_xLN.groupby(['LLAVE_', '/ERP/FUNCAREA', 'AÑO_SUSC'])[['Primas USD', 'Siniestros USD', 'Comisiones USD', 'Primas', 'Siniestros', 'Comisiones', 'PRIMAS_', 'SINIESTROS_', 'COMISIONES_']].sum().reset_index()
Consulta_Ori_.sort_values(by=['LLAVE_', 'AÑO_SUSC'], inplace=True)
Consulta_Ori_['%Inc_sin'] = Consulta_Ori_.groupby('/ERP/FUNCAREA')['SINIESTROS_'].pct_change()
Consulta_Ori_['%Inc_com'] = Consulta_Ori_.groupby('/ERP/FUNCAREA')['COMISIONES_'].pct_change()
Consulta_Ori_['%Prima'] = Consulta_Ori_.groupby('/ERP/FUNCAREA')['PRIMAS_'].pct_change()
Tablas_S.append(Consulta_Ori_)

Consulta_1_ = ConsultaP_R_S_xLN.groupby(['LLAVE_LN',  '/ERP/FUNCAREA', 'AÑO_SUSC'])[['Primas USD', 'Siniestros USD', 'Comisiones USD', 'Primas', 'Siniestros', 'Comisiones', 'PRIMAS_', 'SINIESTROS_', 'COMISIONES_']].sum().reset_index()
Consulta_1_.sort_values(by=['LLAVE_LN', 'AÑO_SUSC'], inplace=True)
Consulta_1_['%Inc_sin'] = Consulta_1_.groupby('/ERP/FUNCAREA')['SINIESTROS_'].pct_change()
Consulta_1_['%Inc_com'] = Consulta_1_.groupby('/ERP/FUNCAREA')['COMISIONES_'].pct_change()
Consulta_1_['%Prima'] = Consulta_1_.groupby('/ERP/FUNCAREA')['PRIMAS_'].pct_change()
Tablas_S.append(Consulta_1_)

Consulta_2_ = ConsultaP_R_S_xLN.groupby(['LLAVE_LN_TR', '/ERP/FUNCAREA', 'ZTIPOREAS', 'AÑO_SUSC'])[['Primas USD', 'Siniestros USD', 'Comisiones USD', 'Primas', 'Siniestros', 'Comisiones', 'PRIMAS_', 'SINIESTROS_', 'COMISIONES_']].sum().reset_index()
Consulta_2_.sort_values(by=['/ERP/FUNCAREA', 'ZTIPOREAS', 'AÑO_SUSC'], inplace=True)
Consulta_2_['%Inc_sin'] = Consulta_2_.groupby('ZTIPOREAS')['SINIESTROS_'].pct_change()
Consulta_2_['%Inc_com'] = Consulta_2_.groupby('ZTIPOREAS')['COMISIONES_'].pct_change()
Consulta_2_['%Prima'] = Consulta_2_.groupby('ZTIPOREAS')['PRIMAS_'].pct_change()
Tablas_S.append(Consulta_2_)

Consulta_3_ = ConsultaP_R_S_xLN.groupby(['LLAVE_LN_R', '/ERP/FUNCAREA', 'Ramo_y', 'AÑO_SUSC'])[['Primas USD', 'Siniestros USD', 'Comisiones USD', 'Primas', 'Siniestros', 'Comisiones', 'PRIMAS_', 'SINIESTROS_', 'COMISIONES_']].sum().reset_index()
Consulta_3_.sort_values(by=['/ERP/FUNCAREA', 'Ramo_y', 'AÑO_SUSC'], inplace=True)
Consulta_3_['%Inc_sin'] = Consulta_3_.groupby('Ramo_y')['SINIESTROS_'].pct_change()
Consulta_3_['%Inc_com'] = Consulta_3_.groupby('Ramo_y')['COMISIONES_'].pct_change()
Consulta_3_['%Prima'] = Consulta_3_.groupby('Ramo_y')['PRIMAS_'].pct_change()
Tablas_S.append(Consulta_3_)

Consulta_4_ = ConsultaP_R_S_xLN.groupby(['LLAVE_LN_T', '/ERP/FUNCAREA', 'ZREGIONRP', 'AÑO_SUSC'])[['Primas USD', 'Siniestros USD', 'Comisiones USD', 'Primas', 'Siniestros', 'Comisiones', 'PRIMAS_', 'SINIESTROS_', 'COMISIONES_']].sum().reset_index()
Consulta_4_.sort_values(by=['/ERP/FUNCAREA', 'ZREGIONRP', 'AÑO_SUSC'], inplace=True)
Consulta_4_['%Inc_sin'] = Consulta_4_.groupby('ZREGIONRP')['SINIESTROS_'].pct_change()
Consulta_4_['%Inc_com'] = Consulta_4_.groupby('ZREGIONRP')['COMISIONES_'].pct_change()
Consulta_4_['%Prima'] = Consulta_4_.groupby('ZREGIONRP')['PRIMAS_'].pct_change()
Tablas_S.append(Consulta_4_)

Consulta_5_ = ConsultaP_R_S_xLN.groupby(['LLAVE_LN_TR_R', '/ERP/FUNCAREA', 'ZTIPOREAS', 'Ramo_y', 'AÑO_SUSC'])[['Primas USD', 'Siniestros USD', 'Comisiones USD', 'Primas', 'Siniestros', 'Comisiones', 'PRIMAS_', 'SINIESTROS_', 'COMISIONES_']].sum().reset_index()
Consulta_5_.sort_values(by=['/ERP/FUNCAREA', 'ZTIPOREAS', 'Ramo_y', 'AÑO_SUSC'], inplace=True)
Consulta_5_['%Inc_sin'] = Consulta_5_.groupby('Ramo_y')['SINIESTROS_'].pct_change()
Consulta_5_['%Inc_com'] = Consulta_5_.groupby('Ramo_y')['COMISIONES_'].pct_change()
Consulta_5_['%Prima'] = Consulta_5_.groupby('Ramo_y')['PRIMAS_'].pct_change()
Tablas_S.append(Consulta_5_)

for df in Tablas_S:
    # Cálculos de porcentajes
    df['%Sin_r'] = df.apply(lambda row: row['Siniestros USD'] / row['Primas USD'] if row['Primas USD'] != 0 else 0, axis=1)
    df['%Com_r'] = df.apply(lambda row: row['Comisiones USD'] / row['Primas USD'] if row['Primas USD'] != 0 else 0, axis=1)
    df['%Sin_p'] = df.apply(lambda row: row['Siniestros'] / row['Primas'] if row['Primas'] != 0 else 0, axis=1)
    df['%Com_p'] = df.apply(lambda row: row['Comisiones'] / row['Primas'] if row['Primas'] != 0 else 0, axis=1)
    df['%Sin'] = df.apply(lambda row: row['SINIESTROS_'] / row['PRIMAS_'] if row['PRIMAS_'] != 0 else 0, axis=1)
    df['%Com'] = df.apply(lambda row: row['COMISIONES_'] / row['PRIMAS_'] if row['PRIMAS_'] != 0 else 0, axis=1)




nombres_hojas = ['CONT_COMP', 'CONT_LN', 'CONT_LN_TR', 'CONT_LN_R', 'CONT_LN_T', 'CONT_LN_TR_R'] 
xFolder = fr"C:\Users\mocamachol\OneDrive - GPV\Planeación Financiera RPAT - Documents\Presupuestos\2026\3_Validacion\xls"
with pd.ExcelWriter(f"{xFolder}\\SinGS_Consulta_RP_C.xlsx", engine='xlsxwriter') as writer:
    for df, nombre in zip(Tablas_C, nombres_hojas):
        df.to_excel(writer, sheet_name=nombre, index=False)

nombres_hojas = ['SUSC_COMP', 'SUSC_LN', 'SUSC_LN_TR', 'SUSC_LN_R', 'SUSC_LN_T', 'SUSC_LN_TR_R'] 
with pd.ExcelWriter(f"{xFolder}\\SinGS_Consulta_RP_S.xlsx", engine='xlsxwriter') as writer:
    for df, nombre in zip(Tablas_S, nombres_hojas):
        df.to_excel(writer, sheet_name=nombre, index=False)

todas_las_tablas = Tablas_C + Tablas_S
nombres_hojas = ['CONT_COMP', 'CONT_LN', 'CONT_LN_TR', 'CONT_LN_R', 'CONT_LN_T', 'CONT_LN_TR_R', 'SUSC_COMP', 'SUSC_LN', 'SUSC_LN_TR', 'SUSC_LN_R', 'SUSC_LN_T', 'SUSC_LN_TR_R'] 
with pd.ExcelWriter(f"{xFolder}\\SinGS_Consulta_RP.xlsx", engine='xlsxwriter') as writer:
    for df, nombre in zip(todas_las_tablas, nombres_hojas):
        df.to_excel(writer, sheet_name=nombre, index=False)



