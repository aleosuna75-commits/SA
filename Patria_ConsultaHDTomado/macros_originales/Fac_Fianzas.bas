Sub ObtieneRetrosFacOFF()

Worksheets("FacultativoOFF").Activate
Range("B3:CZ1000000").ClearContents
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
                   strwhere = " WHERE T1.aOFF_Año >= " & zAñoIni & " AND T1.aOFF_Año <= " & zAñoFin & ""
            Case "Fecha Inicio de Vigencia"
                   strwhere = " WHERE T1.aOFF_FecVigIni >= CONVERT(datetime,'" & zFechaIni & "',103) AND T1.aOFF_FecVigIni <= CONVERT(datetime,'" & zFechaFin & "',103)"
            Case "Vigente al"
                   strwhere = " WHERE T1.aOFF_FecVigFin >= CONVERT(datetime,'" & zFechaFin & "',103) AND T1.aOFF_FecVigIni <= CONVERT(datetime,'" & zFechaFin & "',103)"
            Case "Fecha de Captura"
                   strwhere = " WHERE T1.aOFF_FecCaptura >= CONVERT(datetime,'" & zFechaIni & "',103) AND T1.aOFF_FecCaptura <= CONVERT(datetime,'" & zFechaFin & "',103)"
        End Select
          

   cn.ConnectionString = CadenaConexion()
    cn.ConnectionTimeout = 999999999
    cn.Open

'TABLA FIANZAS
    
    xSelect = "SELECT T1.aOFF_Contrato,T1.cTER_Id,  T1.cTRE_Id, T1.aOFF_Año,T1.aOFF_NumOferta,T1.aOFF_NumEndoso,T1.cCOR_Id, " & _
             "T1.cCOR_Version,T3.cCOR_RazSocial,T1.cCIA_Id,T1.cCIA_Version,T4.cCIA_RazSocial,T1.aOFF_NumAcepta,T1.cMON_Id,T5.cMON_Nombre,T1.cCAF_Id,T8.cCAF_Nombre,T1.cGRM_Id,T7.cGRM_Nombre, " & _
             "T1.aOFF_Giro,T1.aOFF_NumPoliza,T1.cPAI_Id,T9.cPAI_Nombre,T1.cEND_Id,T1.aOFF_FecOferta,T1.aOFF_FecCaptura,T1.cADO_Id, T10.cADO_Nombre, " & _
             "T1.cBEN_Id,T1.aOFF_Osolidario,T1.aOFF_ObjOpera,T1.aOFF_FecVigIni,T1.aOFF_FecVigFin,T1.aOFF_SumaAfi,T1.aOFF_RetCed,T1.aOFF_RenuevaOferta,T1.aOFF_SumaPt,T1.aOFF_MontoPt,T1.aOFF_EPI100,T1.aOFF_EPIPt, " & _
             "T1.aOFF_Comision,T1.aOFF_Cuota,T1.aOFF_Corretaje,T1.aOFF_RvaPrimas,T1.aOFF_RvaIntereses,T1.aOFF_ImpPrimas,T1.aOFF_ImpInteres,T1.aOFF_ContGarBienes,T1.aOFF_ContGarMt,T1.aOFF_Coaseguro,T1.aOFF_EdoCta,T1.aOFF_AnaFinMes, " & _
             "T1.aOFF_AnaFinAño,T1.aOFF_ActCte,T1.aOFF_Inventarios,T1.aOFF_PasCte,T1.aOFF_ActTotal,T1.aOFF_PasLarPla,T1.aOFF_PasTotal,T1.aOFF_ActFijo,T1.aOFF_Patrimonio,T1.aOFF_VenNetas,T1.aOFF_CosVentas,T1.aOFF_UtiNeta, " & _
             "T1.aOFF_RentRI,T1.aOFF_RentRCS,T1.cMON_IdEdoFin,T1.aOFF_PrimaContMT,T1.aOFF_StrosPagMT,T1.aOFF_Observ,T1.cEMP_IdFor, T1.cEMP_IdRev, T2.cSTC_Nombre , " & _
            "STUFF((SELECT DISTINCT ', ' + CAST(T17.cRAM_Id AS varchar(50)) FROM rSubCubXOFF T17 WHERE T1.aOFF_Contrato=T17.aOFF_Contrato AND T1.cTER_Id=T17.cTER_Id AND T1.aOFF_Año=T17.aOFF_Año AND T1.aOFF_NumOferta=T17.aOFF_NumOferta AND T1.aOFF_NumEndoso=T17.aOFF_NumEndoso FOR XML PATH ('')), 1, 2, '') AS Ramos, " & _
            "STUFF((SELECT DISTINCT ', ' + CAST(T17.cSBR_Id AS varchar(50)) FROM rSubCubXOFF T17 WHERE T1.aOFF_Contrato=T17.aOFF_Contrato AND T1.cTER_Id=T17.cTER_Id AND T1.aOFF_Año=T17.aOFF_Año AND T1.aOFF_NumOferta=T17.aOFF_NumOferta AND T1.aOFF_NumEndoso=T17.aOFF_NumEndoso FOR XML PATH ('')), 1, 2, '') AS Subramos, " & _
            "T12.cCOR_IdCed, T12.aHC_NumContrato, T12.aHC_IdentContrato, T12.aHC_Vig, " & _
            "T12.rCROF_PrcRetro, COALESCE(T13.aHCP_Nombre, T14.aHCNP_Nombre, T15.aHCF_Nombre), COALESCE(T13.aHCP_SinContado, T15.aHCF_SinContado) "
            
            
            
    xFrom = " FROM pDBSirec2.dbo.aOFF_OfertaFianzas as T1 " & _
             "LEFT JOIN cSTC_Situacion as T2 on T1.cSTC_Id = T2.cSTC_Id " & _
             "LEFT JOIN cCOR_Corredor as T3 on T1.cCOR_Id=T3.cCOR_Id AND T1.cCOR_Version=T3.cCOR_Version " & _
             "LEFT JOIN cCIA_Compañia as T4 on T1.cCIA_Id=T4.cCIA_Id AND T1.cCIA_Version=T4.cCIA_Version " & _
             "LEFT JOIN cMON_Mon as T5 on T1.cMON_Id=T5.cMON_Id " & _
             "LEFT JOIN cGRM_GrupoRamo as T7 on T1.cGRM_Id=T7.cGRM_Id " & _
             "LEFT JOIN cCAF_CalidadFac as T8 on T1.cCAF_Id=T8.cCAF_Id " & _
             "LEFT JOIN cPAI_Pais as T9 on T1.cPAI_Id=T9.cPAI_Id " & _
             "LEFT JOIN cADO_Afianzado as T10 on T1.cADO_Id=T10.cADO_Id " & _
             "LEFT JOIN rCROF_CuadroRetroOF as T12 on T1.aOFF_Contrato=T12.aOF_NoContr AND T1.cTER_Id=T12.cTER_Id AND T1.aOFF_Año=T12.aOF_AnioVig AND T1.aOFF_NumOferta=T12.aOF_NoOferta AND T1.aOFF_NumEndoso=T12.aOF_NoEndoso " & _
             "LEFT JOIN aHCP_CedProporcional as T13 on T12.cCOR_IdCed=T13.cCOR_Id AND T12.aHC_NumContrato=T13.aHCP_NumContrato AND T12.aHC_IdentContrato=T13.aHCP_IdentContrato " & _
             "LEFT JOIN aHCNP_CedNoProporcional as T14 on T12.cCOR_IdCed=T14.cCOR_Id AND T12.aHC_NumContrato=T14.aHCNP_NumContrato AND T12.aHC_IdentContrato=T14.aHCNP_IdentContrato " & _
             "LEFT JOIN aHCF_CedFacultativo as T15 on T12.cCOR_IdCed=T15.cCOR_Id AND T12.aHC_NumContrato=T15.aHCF_NumContrato AND T12.aHC_IdentContrato=T15.aHCF_IdentContrato "


    strAct = xSelect & xFrom & strwhere
 
    rsAct.CursorLocation = adUseClient
    rsAct.Open strAct, cn, adOpenDynamic, adLockBatchOptimistic, adCmdText
    Sheets("FacultativoOFF").Select
    Sheets("FacultativoOFF").Range("B3").CopyFromRecordset rsAct
    rsAct.Close

   Set rsAnexo2 = Nothing
   cn.Close
   

End Sub
