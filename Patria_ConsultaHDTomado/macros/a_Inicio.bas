Sub EjecutaTodasLasMacros()

Application.ScreenUpdating = False
Application.DisplayAlerts = False

zTipoFiltro = Range("TipoFiltro")
zAñoIni = Range("AñoIni")
zAñoFin = Range("AñoFin")
zFechaIni = Range("FechaIni")
zFechaFin = Range("FechaFin")


 If zTipoFiltro = "Año Suscripción" Then
        If zAñoIni = "" Or zAñoFin = "" Then
            MsgBox "Favor de ingresar el año en la celda correcta"
        
            Application.DisplayAlerts = True
            Application.ScreenUpdating = True
            Exit Sub
        End If
        
         If zAñoIni > zAñoFin Then
                MsgBox "El año fin debe ser mayor o igual al año de inicio"
                    
                Application.DisplayAlerts = True
                Application.ScreenUpdating = True
                Exit Sub
            End If
        
ElseIf zTipoFiltro <> "Año Suscripción" Then
            If zFechaIni = "" Or zFechaFin = "" Then
                MsgBox "Favor de ingresar la fecha en la celda correcta"
                    
                Application.DisplayAlerts = True
                Application.ScreenUpdating = True
                Exit Sub
            End If
            
            If Range("D18").Value > Range("D19").Value Then
                MsgBox "La fecha final debe ser mayor o igual a la fecha de inicio"
                    
                Application.DisplayAlerts = True
                Application.ScreenUpdating = True
                Exit Sub
            End If
End If

'Call ObtieneRetrosProp_Ivan
Call ObtieneRetrosProp
Call ObtieneRetroNoProp
Call ObtieneRetrosNoProp
Call ObtieneRetrosFacOFD
Call ObtieneRetrosFacOFF
Call ObtieneRetrosFacOFV
Call ObtieneRetrosFacOFVG

' Actualiza la leyenda de la hoja Consulta con la fecha consultada
If IsDate(Worksheets("CONTROL").Range("D19").Value) Then
    Worksheets("Consulta").Range("B4").Value = "Este archivo refleja todos los contratos vigentes al " & Format(Worksheets("CONTROL").Range("D19").Value, "dd/mm/yy")
End If

Worksheets("CONTROL").Activate
Range("FechaEjecución").Value = Now()


Application.ScreenUpdating = True
Application.DisplayAlerts = True

MsgBox "Se actualizaron las hojas correctamente!!!"

End Sub


' Borra los datos de la consulta anterior en todo el ancho de la hoja. Antes se
' borraba solo hasta la columna CZ y quedaban datos viejos a la derecha.
Public Sub LimpiaDatos(ws As Worksheet)
    ws.Range(ws.Cells(3, 2), ws.Cells(ws.Rows.Count, ws.Columns.Count)).ClearContents
End Sub

' La columna A arma la llave del contrato con una formula. Se deja exactamente
' en las filas con datos, para que no queden llaves vacias ("---") debajo
' cuando la consulta trae menos filas que la anterior.
' nFilas es Variant porque en Office de 64 bits Recordset.RecordCount es
' LongPtr y VBA no lo acepta directo en un parametro Long.
Public Sub AjustaColumnaLlave(ws As Worksheet, ByVal nFilas As Variant)
    Dim f As String, n As Long
    n = CLng(nFilas)
    f = ws.Range("A3").Formula
    If Left(f, 1) <> "=" Then Exit Sub
    ws.Range(ws.Range("A4"), ws.Cells(ws.Rows.Count, 1)).ClearContents
    If n > 1 Then ws.Range("A3").Resize(n).Formula = f
End Sub
