Sub EjecutaTodasLasMacros()

Application.ScreenUpdating = False
Application.DisplayAlerts = False

zTipoFiltro = Range("TipoFiltro")
zÁñoIni = Range("AñoIni")
zÁñoFin = Range("AñoFin")
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
