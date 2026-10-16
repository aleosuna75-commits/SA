Attribute VB_Name = "Prop"
Sub ObtieneRetrosProp()

Worksheets("Prop").Activate
LimpiaDatos Sheets("Prop")
zTipoFiltro = Range("TipoFiltro")
zAñoIni = Range("AñoIni")
zAñoFin = Range("AñoFin")
zFechaIni = Range("FechaIni")
zFechaFin = Range("FechaFin")

    Dim cn As New ADODB.Connection
    Dim cmd As New ADODB.Command
    Dim rsAct As New ADODB.Recordset
    Dim strAct As String
    
      
    Select Case zTipoFiltro
    
        Case "Año Suscripción"
            strwhere = " WHERE T1.aHTP_AnioVig >= " & zAñoIni & " AND T1.aHTP_AnioVig <= " & zAñoFin & ""
        Case "Fecha Inicio de Vigencia"
            strwhere = " WHERE T1.aHTP_FecIniPerCub >= CONVERT(datetime,'" & zFechaIni & "',103) AND T1.aHTP_FecIniPerCub<= CONVERT(datetime,'" & zFechaFin & "',103)"
        Case "Vigente al"
            strwhere = " WHERE T1.aHTP_FecFinPerCub >= CONVERT(datetime,'" & zFechaFin & "',103) AND T1.aHTP_FecIniPerCub <= CONVERT(datetime,'" & zFechaFin & "',103)"
        Case "Fecha de Captura"
            strwhere = " WHERE T1.aHTP_FecCaptura >= CONVERT(datetime,'" & zFechaIni & "',103) AND T1.aHTP_FecCaptura <= CONVERT(datetime,'" & zFechaFin & "',103)"
    End Select
     
   cn.ConnectionString = CadenaConexion()
    cn.ConnectionTimeout = 999999999
    cn.Open

'CONSULTAS CON CRUCE DE TABLAS TOMADO
    xSelect = "SELECT T1.cCOR_Id, T1.cCOR_Version, T2.cCOR_RazSocial, T1.cCIA_Id, T1.cCIA_Version, T3.cCIA_RazSocial, T1.aHTP_NoContr,T1.aHTP_AnioVig,T1.cTRE_Id, " & _
            "T1.cTCT_Id, T5.cTCT_Nombre, T1.cCCNT_Id, T6.cCCNT_Nombre, T1.cMON_Id, T4.cMON_Nombre, T1.aHTP_RefOrig,T1.aHTP_EsLider,T1.aHTP_MntLimRes,T1.aHTP_MntLimResExc, " & _
            "T1.aHTP_PrcLimResPt,T1.aHTP_PrcLimResPtExc,T1.aHTP_MntLimResPt,T1.aHTP_MntLimResPtExc,T1.aHTP_CienMntPriEst, T1.aHTP_CienMntPriEstPt,T1.aHTP_CienComisionPt,T1.aHTP_CienRvaPriPt,T1.aHTP_SobComision,T1.aHTP_ComSobUtilidades, " & _
            "T1.aHTP_PrcCorretaje,T1.aHTP_PrcImpSobPrima,T1.aHTP_PrcImpSobInt,T1.aHTP_PrcResEsperado,T1.aHTP_PrcSubNorMed, T1.aHTP_PrcSubNorOcu,T1.aHTP_PrcInteres,T1.cPRD_Id,T1.aHTP_DesdeDias,T1.aHTP_PagenDias,T1.aHTP_RvaStosCta, " & _
            "T1.cFRE_Id,T1.aHTP_CarPri,T1.aHTP_CarSto,T1.aHTP_Bordero,T1.aHTP_MntStoContado,T1.aHTP_MntStoContadoPt, T1.aHTP_TipoCambio,T1.aHTP_FecIniPerCub,T1.aHTP_FecFinPerCub,T1.aHTP_PlaResDia,T1.aHTP_PlaResMes," & _
            "T1.aHTP_ExtDesp,T1.aHTP_ExtLib,T1.aHTP_FecOriginal,T1.aHTP_FecCancelacion,T1.cSCN_Id,T1.aHTP_FecCaptura, T1.cMON_IdCum,T1.aHTP_Observaciones, T1.cEMP_IdFor, T1.cEMP_IdRev, " & _
            "T1.aHTP_FecExpedicion,T1.aHTP_CienMntPriEstEXC,T1.aHTP_CienMntPriEstPtEXC,T1.aHTP_CienComisionPtEXC, T1.aHTP_CienRvaPriPtEXC,T1.aHTP_PrcComCartComH,T1.aHTP_PrcComCartIndH,T1.aHTP_PrcComCartVivH, " & _
            "T1.aHTP_PrcComCartComT,T1.aHTP_PrcComCartIndT,T1.aHTP_PrcComCartVivT,T1.aHTP_VigMaxFianzas, T1.aHTP_EsSoftRetro,T1.aHTP_EsBouquet,T1.aHTP_EsNegMGA,T1.aHTP_Utilidades,T1.aHTP_Sobre, " & _
            "T1.aHTP_EsComEscalonada,T1.aHTP_comEscalonadaStdlMax,T1.aHTP_comEscalonadaMax,T1.aHTP_comEscalonadaStdlMin, T1.aHTP_escalonada,T1.aHTP_ProcentajeGR,T1.aHTP_Extincion,T1.aHTP_tasaMinima,T1.aHTP_resultadoHistorico, " & _
            "T1.aHTP_anioResultadoHistorico,T1.aHTP_comisionAdicional,T1.aHTP_comSntdl,T1.aHTP_CarPriPorFijo, T1.aHTP_CarStoPorPend , " & _
            "STUFF((SELECT DISTINCT ', ' + CAST(T7.cRAM_Id AS varchar(50)) FROM rSBRXHTP T7 WHERE T1.cCOR_Id=T7.cCOR_Id AND T1.cCOR_Version=T7.cCOR_Version AND T1.cCIA_Id=T7.cCIA_Id AND T1.cCIA_Version=T7.cCIA_Version AND T1.aHTP_NoContr=T7.aHTP_NoContr AND T1.aHTP_AnioVig=T7.aHTP_AnioVig FOR XML PATH ('')), 1, 2, '') AS Ramos, " & _
            "STUFF((SELECT DISTINCT ', ' + CAST(T7.cSBP_Id AS varchar(50)) FROM rSBRXHTP T7 WHERE T1.cCOR_Id=T7.cCOR_Id AND T1.cCOR_Version=T7.cCOR_Version AND T1.cCIA_Id=T7.cCIA_Id AND T1.cCIA_Version=T7.cCIA_Version AND T1.aHTP_NoContr=T7.aHTP_NoContr AND T1.aHTP_AnioVig=T7.aHTP_AnioVig FOR XML PATH ('')), 1, 2, '') AS Subramos, " & _
            "STUFF((SELECT DISTINCT ', ' + CAST(T0.cPAI_Id AS varchar(50)) FROM rPACXHTP T0 WHERE T1.cCOR_Id=T0.cCOR_Id AND T1.cCOR_Version=T0.cCOR_Version AND T1.cCIA_Id=T0.cCIA_Id AND T1.cCIA_Version=T0.cCIA_Version AND T1.aHTP_NoContr=T0.aHTP_NoContr AND T1.aHTP_AnioVig=T0.aHTP_AnioVig FOR XML PATH ('')), 1, 2, '') AS Paises "
            
    
    xFrom = " FROM pDBSirec2.dbo.aHTP_HojDesTP as T1 " & _
             "LEFT JOIN cCOR_Corredor as T2 on T1.cCOR_Id=T2.cCOR_Id AND T1.cCOR_Version=T2.cCOR_Version " & _
             "LEFT JOIN cCIA_Compañia as T3 on T1.cCIA_Id=T3.cCIA_Id AND T1.cCIA_Version=T3.cCIA_Version " & _
             "LEFT JOIN cMON_Mon as T4 on T1.cMON_Id=T4.cMON_Id " & _
             "LEFT JOIN cTCT_TipoContrato as T5 on T1.cTCT_Id=T5.cTCT_Id AND T1.cTRE_Id=T5.cTRE_Id " & _
             "LEFT JOIN cCCNT_CalContrato as T6 on T1.cCCNT_Id=T6.cCCNT_Id "

' Sin cuadro de retrocesion (T12-T15): repetia el contrato una vez por cada
' contrato de retro. Tambien se quitaron T16 (cEMP_Empleado) y T17 (rPCRXHTP),
' que no aportaban columnas y T17 repetia el contrato por cada ramo/subramo.



 strAct = xSelect & xFrom & strwhere

 rsAct.CursorLocation = adUseClient
    rsAct.Open strAct, cn, adOpenDynamic, adLockBatchOptimistic, adCmdText
    Sheets("Prop").Select
    Sheets("Prop").Range("B3").CopyFromRecordset rsAct
    AjustaColumnaLlave Sheets("Prop"), rsAct.RecordCount

   Set rsAnexo2 = Nothing
   cn.Close
   

End Sub
