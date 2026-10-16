Sub ObtieneRetroNoProp()

Worksheets("NoProp").Activate
Range("B3:CZ1000000").ClearContents
zTipoFiltro = Range("TipoFiltro")
zÁñoIni = Range("AñoIni")
zÁñoFin = Range("AñoFin")
zFechaIni = Range("FechaIni")
zFechaFin = Range("FechaFin")


    Dim cn As New ADODB.Connection
    Dim cmd As New ADODB.Command
    Dim rsAct As New ADODB.Recordset
    Dim strAct As String
           
    Select Case zTipoFiltro
    
        Case "Año Suscripción"
            strwhere = " WHERE T1.aHTNP_AnioVig >= " & zAñoIni & " AND T1.aHTNP_AnioVig <= " & zAñoFin & ""
        Case "Fecha Inicio de Vigencia"
            strwhere = " WHERE T1.aHTNP_FecIniPerCub >= CONVERT(datetime,'" & zFechaIni & "',103) AND T1.aHTNP_FecIniPerCub <= CONVERT(datetime,'" & zFechaFin & "',103)"
        Case "Vigente al"
            strwhere = " WHERE T1.aHTNP_FecFinPerCub >= CONVERT(datetime,'" & zFechaFin & "',103) AND T1.aHTNP_FecIniPerCub <= CONVERT(datetime,'" & zFechaFin & "',103)"
        Case "Fecha de Captura"
            strwhere = " WHERE T1.aHTNP_FecCaptura >= CONVERT(datetime,'" & zFechaIni & "',103) AND T1.aHTNP_FecCaptura <= CONVERT(datetime,'" & zFechaFin & "',103)"
    End Select
           
           
    cn.ConnectionString = CadenaConexion()
    cn.ConnectionTimeout = 999999999
    cn.Open



'CONSULTAS CON CRUCE DE TABLAS TOMADO

    xSelect = "SELECT T1.cCOR_Id,T1.cCOR_Version,T2.cCOR_RazSocial,T1.cCIA_Id,T1.cCIA_Version,T3.cCIA_RazSocial,T1.aHTNP_NoContr,T1.aHTNP_AnioVig,T1.cTRE_Id, " & _
            "T1.cTCT_Id,T5.cTCT_Nombre,T1.cCCNT_Id,T6.cCCNT_Nombre,T1.cMON_Id,T4.cMON_Nombre,T1.aHTNP_RefOrig,T1.aHTNP_EsLider,T1.aHTNP_EsGarantia,T1.aHTNP_MntLimRes, " & _
            "T1.aHTNP_PrcLimResPt,T1.aHTNP_MntLimResPt,T1.aHTNP_MntPrioridad,T1.aHTNP_MntPriMinDep,T1.aHTNP_MntPriMinDepPt, " & _
            "T1.aHTNP_MntPriEst,T1.aHTNP_MntPriEstPt,T1.aHTNP_NegPro,T1.aHTNP_MntPriPro,T1.aHTNP_MntTEV,T1.aHTNP_MntHuracan, " & _
            "T1.aHTNP_MntImpuesto,T1.aHTNP_MntCorretaje,T1.cPRD_Id,T1.aHTNP_Garantia,T1.aHTNP_TipoCambio,T1.aHTNP_Ajuste, " & _
            "T1.aHTNP_FecIniPerCub,T1.aHTNP_FecFinPerCub,T1.aHTNP_FecOriginal,T1.aHTNP_FecCancelacion,T1.cMON_IdCum, " & _
            "T1.aHTNP_Observaciones,T1.cEMP_IdFor, T1.cEMP_IdRev, " & _
            "T1.aHTNP_FecExpedicion,T1.aHTNP_PrcComCartComH,T1.aHTNP_PrcComCartIndH,T1.aHTNP_PrcComCartVivH, " & _
            "T1.aHTNP_PrcComCartComT,T1.aHTNP_PrcComCartIndT,T1.aHTNP_PrcComCartVivT,T1.aHTNP_MntCumMax,T1.aHTNP_MntCumMaxH, " & _
            "T1.aHTNP_FecCaptura,T1.aHTNP_VigMaxFianzas,T1.aHTNP_EsSoftRetro,T1.aHTNP_ComReaseguro,T1.aHTNP_ISR, " & _
            "STUFF((SELECT DISTINCT ', ' + CAST(T7.cRAM_Id AS varchar(50)) FROM rSBRXHTNP T7 WHERE T1.cCOR_Id=T7.cCOR_Id AND T1.cCOR_Version=T7.cCOR_Version AND T1.cCIA_Id=T7.cCIA_Id AND T1.cCIA_Version=T7.cCIA_Version AND T1.aHTNP_NoContr=T7.aHTNP_NoContr AND T1.aHTNP_AnioVig=T7.aHTNP_AnioVig FOR XML PATH ('')), 1, 2, '') AS Ramos, " & _
            "STUFF((SELECT DISTINCT ', ' + CAST(T7.cSBP_Id AS varchar(50)) FROM rSBRXHTNP T7 WHERE T1.cCOR_Id=T7.cCOR_Id AND T1.cCOR_Version=T7.cCOR_Version AND T1.cCIA_Id=T7.cCIA_Id AND T1.cCIA_Version=T7.cCIA_Version AND T1.aHTNP_NoContr=T7.aHTNP_NoContr AND T1.aHTNP_AnioVig=T7.aHTNP_AnioVig FOR XML PATH ('')), 1, 2, '') AS Subramos, " & _
            "STUFF((SELECT DISTINCT ', ' + CAST(T0.cPAI_Id AS varchar(50)) FROM rPACXHTNP T0 WHERE T1.cCOR_Id=T0.cCOR_Id AND T1.cCOR_Version=T0.cCOR_Version AND T1.cCIA_Id=T0.cCIA_Id AND T1.cCIA_Version=T0.cCIA_Version AND T1.aHTNP_NoContr=T0.aHTNP_NoContr AND T1.aHTNP_AnioVig=T0.aHTNP_AnioVig FOR XML PATH ('')), 1, 2, '') AS Paises, " & _
            "T12.cCOR_IdCed, T12.aHC_NumContrato, T12.aHC_IdentContrato, " & _
            "T12.aHC_Vig, T12.rCRHD_PrcRetro, COALESCE(T13.aHCP_Nombre, T14.aHCNP_Nombre, T15.aHCF_Nombre), COALESCE(T13.aHCP_SinContado, T15.aHCF_SinContado), " & _
            "T18.aHTNP_Renglon AS Capa, T19.cTCT_NomCorto AS Tipo_Capa, T18.rCAP_MntRespon AS MtoResponsabilidad, T18.rCAP_MntPriori AS MtoPrioridad_Capa, " & _
            "T18.rCAP_MntMinimo AS MtoMinimo, T18.rCAP_MntMaximo AS MtoMaximo, T18.rCAP_PrcLimPt AS PrcLimitePt, T18.rCAP_MntPrimEst AS MtoPrimaEst "
            
            
            
    xFrom = " FROM pDBSirec2.dbo.aHTNP_HojDesTNP as T1 " & _
             "LEFT JOIN cCOR_Corredor as T2 on T1.cCOR_Id=T2.cCOR_Id AND T1.cCOR_Version=T2.cCOR_Version " & _
             "LEFT JOIN cCIA_Compañia as T3 on T1.cCIA_Id=T3.cCIA_Id AND T1.cCIA_Version=T3.cCIA_Version " & _
             "LEFT JOIN cMON_Mon as T4 on T1.cMON_Id=T4.cMON_Id " & _
             "LEFT JOIN cTCT_TipoContrato as T5 on T1.cTCT_Id=T5.cTCT_Id AND T1.cTRE_Id=T5.cTRE_Id " & _
             "LEFT JOIN cCCNT_CalContrato as T6 on T1.cCCNT_Id=T6.cCCNT_Id " & _
             "LEFT JOIN rCRHD_CuadroRetroHD as T12 on T1.cCOR_Id=T12.cCOR_Id AND T1.cCIA_Id=T12.cCIA_Id AND T1.aHTNP_NoContr=T12.aHT_NoContr AND T1.aHTNP_AnioVig=T12.aHT_AnioVig " & _
             "LEFT JOIN aHCP_CedProporcional as T13 on T12.cCOR_IdCed=T13.cCOR_Id AND T12.aHC_NumContrato=T13.aHCP_NumContrato AND T12.aHC_IdentContrato=T13.aHCP_IdentContrato " & _
             "LEFT JOIN aHCNP_CedNoProporcional as T14 on T12.cCOR_IdCed=T14.cCOR_Id AND T12.aHC_NumContrato=T14.aHCNP_NumContrato AND T12.aHC_IdentContrato=T14.aHCNP_IdentContrato " & _
             "LEFT JOIN aHCF_CedFacultativo as T15 on T12.cCOR_IdCed=T15.cCOR_Id AND T12.aHC_NumContrato=T15.aHCF_NumContrato AND T12.aHC_IdentContrato=T15.aHCF_IdentContrato " & _
             "LEFT JOIN rCAPXHTNP as T18 on T1.cCOR_Id=T18.cCOR_Id AND T1.cCOR_Version=T18.cCOR_Version AND T1.cCIA_Id=T18.cCIA_Id AND T1.cCIA_Version=T18.cCIA_Version AND T1.aHTNP_NoContr=T18.aHTNP_NoContr AND T1.aHTNP_AnioVig=T18.aHTNP_AnioVig " & _
             "LEFT JOIN cTCT_TipoContrato as T19 on T18.cTRE_Id=T19.cTRE_Id AND T18.cTCT_Id=T19.cTCT_Id "

' strAct = "SELECT DISTINCT * FROM ( " & xSelect & xFrom & strwhere & " )"
 strAct = xSelect & xFrom & strwhere
 
 rsAct.CursorLocation = adUseClient
    rsAct.Open strAct, cn, adOpenDynamic, adLockBatchOptimistic, adCmdText
    Sheets("NoProp").Select
    Sheets("NoProp").Range("B3").CopyFromRecordset rsAct
  
   Set rsAnexo2 = Nothing
   cn.Close
   

End Sub
