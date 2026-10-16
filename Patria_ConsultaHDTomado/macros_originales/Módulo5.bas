Sub ObtieneRetrosProp_Ivan()

Worksheets("Prop").Activate
Range("A3:BR1000000").ClearContents
zTipoFiltro = Range("TipoFiltro")
zAñoIni = Range("AñoIni")
zAñoFin = Range("AñoFin")
zFechaIni = Range("FechaIni")
zFechaFin = Range("FechaFin")

    Dim cn As New ADODB.Connection
    Dim cmd As New ADODB.Command
    Dim rsAct As New ADODB.Recordset
    Dim strAct As String
    
     
   cn.ConnectionString = CadenaConexion()
    cn.ConnectionTimeout = 999999999
    cn.Open

'CONSULTAS CON CRUCE DE TABLAS TOMADO
    strAct = "SELECT T1.cCOR_Id, T1.cCOR_Version, T2.cCOR_RazSocial, T1.cCIA_Id, T1.cCIA_Version, T3.cCIA_RazSocial, T1.aHTP_NoContr,T1.aHTP_AnioVig,T1.cTRE_Id, " & _
            "T1.cTCT_Id, T5.cTCT_Nombre, T1.cCCNT_Id, T6.cCCNT_Nombre, T1.cMON_Id, T4.cMON_Nombre, T1.aHTP_RefOrig " & _
             "FROM pDBSirec2.dbo.aHTP_HojDesTP as T1 " & _
             "LEFT JOIN cCOR_Corredor as T2 on T1.cCOR_Id=T2.cCOR_Id AND T1.cCOR_Version=T2.cCOR_Version " & _
             "LEFT JOIN cCIA_Compañia as T3 on T1.cCIA_Id=T3.cCIA_Id AND T1.cCIA_Version=T3.cCIA_Version " & _
             "LEFT JOIN cMON_Mon as T4 on T1.cMON_Id=T4.cMON_Id " & _
             "LEFT JOIN cTCT_TipoContrato as T5 on T1.cTCT_Id=T5.cTCT_Id AND T1.cTRE_Id=T5.cTRE_Id " & _
             "LEFT JOIN cCCNT_CalContrato as T6 on T1.cCCNT_Id=T6.cCCNT_Id "



 rsAct.CursorLocation = adUseClient
    rsAct.Open strAct, cn, adOpenDynamic, adLockBatchOptimistic, adCmdText
    Sheets("Prop").Select
    Sheets("Prop").Range("A3").CopyFromRecordset rsAct
  
   Set rsAnexo2 = Nothing
   cn.Close
   

End Sub
