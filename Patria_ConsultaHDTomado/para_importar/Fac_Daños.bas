Attribute VB_Name = "Fac_Daños"
Sub ObtieneRetrosFacOFD()

Worksheets("FacultativoOFD").Activate
LimpiaDatos Sheets("FacultativoOFD")
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
            strwhere = " WHERE T1.aOFD_AnioVig >= " & zAñoIni & " AND T1.aOFD_AnioVig <= " & zAñoFin & ""
        Case "Fecha Inicio de Vigencia"
            strwhere = " WHERE T1.aOFD_FecIniVig >= CONVERT(datetime,'" & zFechaIni & "',103) AND T1.aOFD_FecIniVig <= CONVERT(datetime,'" & zFechaFin & "',103)"
        Case "Vigente al"
            strwhere = " WHERE T1.aOFD_FecFinVig >= CONVERT(datetime,'" & zFechaFin & "',103) AND T1.aOFD_FecIniVig <= CONVERT(datetime,'" & zFechaFin & "',103)"
        Case "Fecha de Captura"
            strwhere = " WHERE T1.aOFD_FecCaptura >= CONVERT(datetime,'" & zFechaIni & "',103) AND T1.aOFD_FecCaptura <= CONVERT(datetime,'" & zFechaFin & "',103)"
    End Select
                
           
           
   cn.ConnectionString = CadenaConexion()
    cn.ConnectionTimeout = 999999999
    cn.Open

'CONSULTAS CON CRUCE DE TABLAS TOMADO
'TABLA DAÑOS
    

    xSelect = "SELECT T1.aOFD_NoContr,T1.aOFD_AnioVig,T1.aOFD_NoOferta,T1.aOFD_NoEndoso,T1.aOFD_NoAcep,T1.cCOR_Id, T1.cCOR_Version,T3.cCOR_RazSocial,T1.cCIA_Id,T1.cCIA_Version,T4.cCIA_RazSocial,T1.cTER_Id,T1.cTRE_Id,T1.cTCT_Id,T6.cTCT_Nombre, " & _
            "T1.cMON_Id,T5.cMON_Nombre,T1.cGRM_Id,T7.cGRM_Nombre,T1.cCAF_Id,T8.cCAF_Nombre,T1.cCAR_Id, " & _
            "T1.aOFD_GiroEsp,T1.aOFD_NoPoliza,T1.aOFD_EsLider,T1.aOFD_FecOferta,T1.aOFD_FecCaptura,T1.cEND_Id,T1.cAMO_Id, T10.cAMO_Nombre, " & _
            "T1.aOFD_FecIniVig,T1.aOFD_FecFinVig,T1.cPAI_Id,T9.cPAI_Nombre,T1.aOFD_SubLim,T1.aOFD_BienAse,T1.aOFD_Renueva, " & _
            "T1.aOFD_MntSumAse,T1.aOFD_MntPriRgo,T1.aOFD_PrcAceptPt,T1.aOFD_MntAceptPt,T1.aOFD_MntEpiPtCapa, " & _
            "T1.aOFD_MntCobCapa,T1.aOFD_MntSumAseMyT,T1.aOFD_PrcCuota,T1.aOFD_PrcRvaPrimas,T1.aOFD_MntPriEst, " & _
            "T1.aOFD_MntPriEstPt,T1.aOFD_Comision,T1.aOFD_PrcIntRes,T1.aOFD_PrcCorretaje,T1.aOFD_PrcImpPrimas, " & _
            "T1.aOFD_PrcImpInter,T1.aOFD_EdoCta,T1.aOFD_Deducibles,T1.aOFD_MntTerrDaFis,T1.aOFD_PrcTerrDaFis, " & _
            "T1.aOFD_MntRHidrDaFis,T1.aOFD_PrcRHidrDaFis,T1.aOFD_MntTerrLuCes,T1.aOFD_PrcTerrLuCes, " & _
            "T1.aOFD_MntRHidrLuCes,T1.aOFD_PrcRHidrLuCes,T1.aOFD_CoaAsegurado,T1.aOFD_MntCoAsegurado, " & _
            "T1.aOFD_PrcCoAsegurado,T1.aOFD_CoaCedente,T1.aOFD_MntRetCed,T1.cMON_IdTer,T1.aOFD_MntTerr,T1.cMON_IdHur, " & _
            "T1.aOFD_MntHur,T1.aOFD_MntPriCont,T1.aOFD_MntStroPag,T1.aOFD_AviAnio,T1.aOFD_AviModelo,T1.aOFD_AviAeroNave, " & _
            "T1.aOFD_AviMarca,T1.aOFD_AviNoSerie,T1.aOFD_AviMatricula,T1.aOFD_AviNoPas,T1.aOFD_AviNoTrip,T1.aOFD_AviAerop, " & _
            "T1.aOFD_AjusteMer,T1.aOFD_MntAjuMerEPI,T1.aOFD_MntAjuMerEPIPt,T1.aOFD_MntSumAseMV,T1.aOFD_MntTotDllMV, T1.aOFD_Observ,T1.cEMP_IdFor, T1.cEMP_IdRev, T2.cSTC_Nombre , " & _
            "STUFF((SELECT DISTINCT ', ' + CAST(T17.cRAM_Id AS varchar(50)) FROM rSBRXOFD T17 WHERE T1.aOFD_NoContr=T17.aOFD_NoContr AND T1.cTER_Id=T17.cTER_Id AND T1.aOFD_AnioVig=T17.aOFD_AnioVig AND T1.aOFD_NoOferta=T17.aOFD_NoOferta AND T1.aOFD_NoEndoso=T17.aOFD_NoEndoso FOR XML PATH ('')), 1, 2, '') AS Ramos, " & _
            "STUFF((SELECT DISTINCT ', ' + CAST(T17.cSBP_Id AS varchar(50)) FROM rSBRXOFD T17 WHERE T1.aOFD_NoContr=T17.aOFD_NoContr AND T1.cTER_Id=T17.cTER_Id AND T1.aOFD_AnioVig=T17.aOFD_AnioVig AND T1.aOFD_NoOferta=T17.aOFD_NoOferta AND T1.aOFD_NoEndoso=T17.aOFD_NoEndoso FOR XML PATH ('')), 1, 2, '') AS Subramos "
            
            
            
    xFrom = " FROM pDBSirec2.dbo.aOFD_OfertaD as T1 " & _
             "LEFT JOIN cSTC_Situacion as T2 on T1.cSTC_Id=T2.cSTC_Id " & _
             "LEFT JOIN cCOR_Corredor as T3 on T1.cCOR_Id=T3.cCOR_Id AND T1.cCOR_Version=T3.cCOR_Version " & _
             "LEFT JOIN cCIA_Compañia as T4 on T1.cCIA_Id=T4.cCIA_Id AND T1.cCIA_Version=T4.cCIA_Version " & _
             "LEFT JOIN cMON_Mon as T5 on T1.cMON_Id=T5.cMON_Id " & _
             "LEFT JOIN cTCT_TipoContrato as T6 on T1.cTCT_Id=T6.cTCT_Id AND T1.cTRE_Id=T6.cTRE_Id " & _
             "LEFT JOIN cGRM_GrupoRamo as T7 on T1.cGRM_Id=T7.cGRM_Id " & _
             "LEFT JOIN cCAF_CalidadFac as T8 on T1.cCAF_Id=T8.cCAF_Id " & _
             "LEFT JOIN cPAI_Pais as T9 on T1.cPAI_Id=T9.cPAI_Id " & _
             "LEFT JOIN cAMO_AseguradoMoral as T10 on T1.cAMO_Id=T10.cAMO_Id "

' Sin cuadro de retrocesion (T12-T15): repetia la oferta una vez por cada
' contrato de retro.

' strAct = "SELECT DISTINCT * FROM ( " & xSelect & xFrom & strwhere & " )"
 strAct = xSelect & xFrom & strwhere
 
 rsAct.CursorLocation = adUseClient
    rsAct.Open strAct, cn, adOpenDynamic, adLockBatchOptimistic, adCmdText
    Sheets("FacultativoOFD").Select
    Sheets("FacultativoOFD").Range("B3").CopyFromRecordset rsAct
    AjustaColumnaLlave Sheets("FacultativoOFD"), rsAct.RecordCount
    rsAct.Close

   Set rsAnexo2 = Nothing
   cn.Close
   

End Sub
