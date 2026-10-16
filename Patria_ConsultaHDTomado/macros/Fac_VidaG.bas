Sub ObtieneRetrosFacOFVG()

Worksheets("FacultativoOFVG").Activate
LimpiaDatos Sheets("FacultativoOFVG")
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
               strwhere = " WHERE T1.aOFVG_AñoVig >= " & zAñoIni & " AND T1.aOFVG_AñoVig <= " & zAñoFin & ""
        Case "Fecha Inicio de Vigencia"
               strwhere = " WHERE T1.aOFVG_FecIniVig >= CONVERT(datetime,'" & zFechaIni & "',103) AND T1.aOFVG_FecIniVig <= CONVERT(datetime,'" & zFechaFin & "',103)"
        Case "Vigente al"
               strwhere = " WHERE T1.aOFVG_FecFinVig >= CONVERT(datetime,'" & zFechaFin & "',103) AND T1.aOFVG_FecIniVig <= CONVERT(datetime,'" & zFechaFin & "',103)"
        Case "Fecha de Captura"
               strwhere = " WHERE T1.aOFVG_FecCaptura >= CONVERT(datetime,'" & zFechaIni & "',103) AND T1.aOFVG_FecCaptura <= CONVERT(datetime,'" & zFechaFin & "',103)"
    End Select

    cn.ConnectionString = CadenaConexion()
    cn.ConnectionTimeout = 999999999
    cn.Open
    

'TABLA VIDA GRUPO
    strAct = "SELECT T1.aOFVG_NumContr,T1.cTER_Id,T1.cTRE_Id,T1.aOFVG_AñoVig,T1.aOFVG_NumOfer,T1.aOFVG_NumEnd,T1.aOFVG_NumAcept, " & _
            "T1.cCOR_Id,T1.cCOR_Ver,T3.cCOR_RazSocial,T1.cCIA_Id,T1.cCIA_Ver,T4.cCIA_RazSocial,T1.cMON_Id,T5.cMON_Nombre,T1.cGRM_Id,T7.cGRM_Nombre,T1.cCAF_Id,T8.cCAF_Nombre,T1.cENDOFV_Id, " & _
            "T1.aOFVG_CancDef,T1.aOFVG_FecOfer,T1.aOFVG_FecCaptura,T1.cGADO_Id,T1.cPLOFV_Id,T1.cOFVG_MntMax,T1.cOFVG_AcumMax,T1.cOFVG_SAMI, " & _
            "T1.cOFVG_MntProm,T1.cOFVG_PrimaCien,T1.cOFVG_Div,T1.cOFVG_ComDto,T1.cOFVG_DeducTot,T1.aOFVG_NumPol, " & _
            "T1.aOFVG_NumAseg,T1.aOFVG_EdadProm,T1.aOFVG_EdadMax,T1.aOFVG_NumCert,T1.aOFVG_ComReas,T1.aOFVG_PrcRvaPrimas, " & _
            "T1.aOFVG_PrcInts,T1.aOFVG_PrcCorje,T1.aOFVG_PrcImptoPrim,T1.aOFVG_PrcImptoInts,T1.aOFVG_FecIniVig, " & _
            "T1.aOFVG_FecFinVig,T1.aOFVG_OferStro,T1.aOFVG_Exclu,T1.aOFVG_CondEsp,T1.aOFVG_RgaSumaAseg,T1.aOFVG_Obs, " & _
            "T1.cEMP_IdFor, T1.cEMP_IdRev, T2.cSTC_Nombre  " & _
             "FROM pDBSirec2.dbo.aOFVG_OferVidaGpo as T1 " & _
             "LEFT JOIN cSTC_Situacion as T2 on T1.cSTC_Id = T2.cSTC_Id " & _
             "LEFT JOIN cCOR_Corredor as T3 on T1.cCOR_Id=T3.cCOR_Id " & _
             "LEFT JOIN cCIA_Compañia as T4 on T1.cCIA_Id=T4.cCIA_Id " & _
             "LEFT JOIN cMON_Mon as T5 on T1.cMON_Id=T5.cMON_Id " & _
             "LEFT JOIN cGRM_GrupoRamo as T7 on T1.cGRM_Id=T7.cGRM_Id " & _
             "LEFT JOIN cCAF_CalidadFac as T8 on T1.cCAF_Id=T8.cCAF_Id " & _
            strwhere

'IIF(T1.cEMP_IdRev=0, 'PENDIENTE', 'AUTORIZADO')

    xSelect = "SELECT T1.aOFVG_NumContr,T1.cTER_Id,T1.cTRE_Id,T1.aOFVG_AñoVig,T1.aOFVG_NumOfer,T1.aOFVG_NumEnd,T1.aOFVG_NumAcept, " & _
            "T1.cCOR_Id,T1.cCOR_Ver,T3.cCOR_RazSocial,T1.cCIA_Id,T1.cCIA_Ver,T4.cCIA_RazSocial,T1.cMON_Id,T5.cMON_Nombre,T1.cGRM_Id,T7.cGRM_Nombre,T1.cCAF_Id,T8.cCAF_Nombre,T1.cENDOFV_Id, " & _
            "T1.aOFVG_CancDef,T1.aOFVG_FecOfer,T1.aOFVG_FecCaptura,T1.cGADO_Id,T1.cPLOFV_Id,T1.cOFVG_MntMax,T1.cOFVG_AcumMax,T1.cOFVG_SAMI, " & _
            "T1.cOFVG_MntProm,T1.cOFVG_PrimaCien,T1.cOFVG_Div,T1.cOFVG_ComDto,T1.cOFVG_DeducTot,T1.aOFVG_NumPol, " & _
            "T1.aOFVG_NumAseg,T1.aOFVG_EdadProm,T1.aOFVG_EdadMax,T1.aOFVG_NumCert,T1.aOFVG_ComReas,T1.aOFVG_PrcRvaPrimas, " & _
            "T1.aOFVG_PrcInts,T1.aOFVG_PrcCorje,T1.aOFVG_PrcImptoPrim,T1.aOFVG_PrcImptoInts,T1.aOFVG_FecIniVig, " & _
            "T1.aOFVG_FecFinVig,T1.aOFVG_OferStro,T1.aOFVG_Exclu,T1.aOFVG_CondEsp,T1.aOFVG_RgaSumaAseg,T1.aOFVG_Obs, " & _
            "T1.cEMP_IdFor, T1.cEMP_IdRev, T2.cSTC_Nombre, " & _
            "STUFF((SELECT DISTINCT ', ' + CAST(T17.cRAM_Id AS varchar(50)) FROM rSubCubxOFVG T17 WHERE T1.aOFVG_NumContr=T17.aOFVG_NumContr AND T1.cTER_Id=T17.cTER_Id AND T1.aOFVG_AñoVig=T17.aOFVG_AñoVig AND T1.aOFVG_NumOfer=T17.aOFVG_NumOfer AND T1.aOFVG_NumEnd=T17.aOFVG_NumEnd FOR XML PATH ('')), 1, 2, '') AS Ramos, " & _
            "STUFF((SELECT DISTINCT ', ' + CAST(T17.cSBR_Id AS varchar(50)) FROM rSubCubxOFVG T17 WHERE T1.aOFVG_NumContr=T17.aOFVG_NumContr AND T1.cTER_Id=T17.cTER_Id AND T1.aOFVG_AñoVig=T17.aOFVG_AñoVig AND T1.aOFVG_NumOfer=T17.aOFVG_NumOfer AND T1.aOFVG_NumEnd=T17.aOFVG_NumEnd FOR XML PATH ('')), 1, 2, '') AS Subramos "
            
            
            
    xFrom = " FROM pDBSirec2.dbo.aOFVG_OferVidaGpo as T1 " & _
             "LEFT JOIN cSTC_Situacion as T2 on T1.cSTC_Id = T2.cSTC_Id " & _
             "LEFT JOIN cCOR_Corredor as T3 on T1.cCOR_Id=T3.cCOR_Id AND T1.cCOR_Ver=T3.cCOR_Version " & _
             "LEFT JOIN cCIA_Compañia as T4 on T1.cCIA_Id=T4.cCIA_Id AND T1.cCIA_Ver=T4.cCIA_Version " & _
             "LEFT JOIN cMON_Mon as T5 on T1.cMON_Id=T5.cMON_Id " & _
             "LEFT JOIN cGRM_GrupoRamo as T7 on T1.cGRM_Id=T7.cGRM_Id " & _
             "LEFT JOIN cCAF_CalidadFac as T8 on T1.cCAF_Id=T8.cCAF_Id  "

' Sin cuadro de retrocesion (T12-T15): repetia la oferta una vez por cada
' contrato de retro.
' Corredor (T3) y compania (T4) se cruzan tambien por version, como en las
' demas hojas; sin ella la oferta salia una vez por cada version del catalogo.


    strAct = xSelect & xFrom & strwhere
 

 rsAct.CursorLocation = adUseClient
    rsAct.Open strAct, cn, adOpenDynamic, adLockBatchOptimistic, adCmdText
    Sheets("FacultativoOFVG").Select
    Sheets("FacultativoOFVG").Range("B3").CopyFromRecordset rsAct
    AjustaColumnaLlave Sheets("FacultativoOFVG"), rsAct.RecordCount
    rsAct.Close

   Set rsAnexo2 = Nothing
   cn.Close
   

End Sub
