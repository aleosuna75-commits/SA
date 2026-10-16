Attribute VB_Name = "Fac_VidaI"
Sub ObtieneRetrosFacOFV()

Worksheets("FacultativoOFV").Activate
LimpiaDatos Sheets("FacultativoOFV")
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
               strwhere = " WHERE T1.aOFV_AñoVig >= " & zAñoIni & " AND T1.aOFV_AñoVig <= " & zAñoFin & ""
        Case "Fecha Inicio de Vigencia"
               strwhere = " WHERE T1.aOFV_FecIniVig >= CONVERT(datetime,'" & zFechaIni & "',103) AND T1.aOFV_FecIniVig <= CONVERT(datetime,'" & zFechaFin & "',103)"
        Case "Vigente al"
               strwhere = " WHERE T1.aOFV_FecFinVig >= CONVERT(datetime,'" & zFechaFin & "',103) AND T1.aOFV_FecIniVig <= CONVERT(datetime,'" & zFechaFin & "',103)"
        Case "Fecha de Captura"
               strwhere = " WHERE T1.aOFV_FecCaptura >= CONVERT(datetime,'" & zFechaIni & "',103) AND T1.aOFV_FecCaptura <= CONVERT(datetime,'" & zFechaFin & "',103)"
    End Select
          
    cn.ConnectionString = CadenaConexion()
    cn.ConnectionTimeout = 999999999
    cn.Open

'TABLA VIDA
    
    xSelect = "SELECT T1.aOFV_NumContr,T1.cTER_Id,T1.cTRE_Id, T1.aOFV_AñoVig,T1.aOFV_NumOfer,T1.aOFV_NumEnd,T1.aOFV_NumAcept,T1.cCOR_Id, " & _
             "T1.cCOR_Ver,T3.cCOR_RazSocial,T1.cCIA_Id,T1.cCIA_Ver,T4.cCIA_RazSocial,T1.cMON_Id,T5.cMON_Nombre,T1.cGRM_Id,T7.cGRM_Nombre,T1.cCAF_Id,T8.cCAF_Nombre,T1.cENDOFV_Id,T1.aOFV_CancDef, " & _
             "T1.aOFV_FecOfer,T1.aOFV_FecCaptura,T1.cAFI_Id,T1.aOFV_NumPol,T1.aOFV_NumCes,T1.aOFV_NumCert,T1.aOFV_IngAnual,T1.aOFV_Nombre, " & _
             "T1.aOFV_CtalTot,T1.cPLOFV_Id,T1.aOFV_OtroSeg,T1.aOFV_BeneNombre,T1.aOFV_TipoBene,T1.aOFV_CotMed,T1.aOFV_CotOcup, " & _
             "T1.aOFV_Acci,T1.aOFV_Inva,T1.aOFV_FecIniVig,T1.aOFV_FecFinVig,T1.aOFV_Prc1erAño,T1.aOFV_PrcRen, " & _
             "T1.aOFV_PrcRvaPrimas,T1.aOFV_PrcInts,T1.aOFV_PrcCorje,T1.aOFV_PrcImptoPrim,T1.aOFV_PrcImptoInts, " & _
             "T1.aOFV_OferStro,T1.aOFV_Obs,T1.cEMP_IdFor, T1.cEMP_IdRev, T2.cSTC_Nombre , " & _
            "STUFF((SELECT DISTINCT ', ' + CAST(T17.cRAM_Id AS varchar(50)) FROM rSubCubxOFV T17 WHERE T1.aOFV_NumContr=T17.aOFV_NumContr AND T1.cTER_Id=T17.cTER_Id AND T1.aOFV_AñoVig=T17.aOFV_AñoVig AND T1.aOFV_NumOfer=T17.aOFV_NumOfer AND T1.aOFV_NumEnd=T17.aOFV_NumEnd FOR XML PATH ('')), 1, 2, '') AS Ramos, " & _
            "STUFF((SELECT DISTINCT ', ' + CAST(T17.cSBR_Id AS varchar(50)) FROM rSubCubxOFV T17 WHERE T1.aOFV_NumContr=T17.aOFV_NumContr AND T1.cTER_Id=T17.cTER_Id AND T1.aOFV_AñoVig=T17.aOFV_AñoVig AND T1.aOFV_NumOfer=T17.aOFV_NumOfer AND T1.aOFV_NumEnd=T17.aOFV_NumEnd FOR XML PATH ('')), 1, 2, '') AS Subramos "
            
            
            
    xFrom = " FROM pDBSirec2.dbo.aOFV_OferVida as T1 " & _
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
    Sheets("FacultativoOFV").Select
    Sheets("FacultativoOFV").Range("B3").CopyFromRecordset rsAct
    AjustaColumnaLlave Sheets("FacultativoOFV"), rsAct.RecordCount
    rsAct.Close

   Set rsAnexo2 = Nothing
   cn.Close
   

End Sub
