Attribute VB_Name = "EncabezadosCapa"
Option Explicit

' Banda "Capas" + subencabezados del detalle por capa, con formato calcado
' de los encabezados existentes, y la columna de % en formato porcentaje.
' Vive en filas 1-2 y en el formato de columna (las macros de consulta no
' los borran), asi que persiste al refrescar.

Sub PonEncabezadosCapa()
    Application.ScreenUpdating = False
    Application.DisplayAlerts = False

    ' Las capas solo van en NoProp_sbr (NoProp es una fila por contrato) y,
    ' sin las columnas de retrocesion, empiezan en BP.
    PonHeader Sheets("NoProp_sbr"), "BO", "BP", "BW"

    Application.CutCopyMode = False
    Application.DisplayAlerts = True
    Application.ScreenUpdating = True
    MsgBox "Encabezados de capa actualizados en NoProp_sbr."
End Sub

Private Sub PonHeader(ws As Worksheet, refCol As String, c1 As String, c2 As String)
    Dim nombres As Variant, i As Long, col As Long
    nombres = Array("Capa", "Tipo", "Mto Responsabilidad", "Mto Prioridad", _
                    "Mto Mínimo", "Mto Máximo", "% Límite Pt", "Mto Prima Est")

    With ws
        .Range(refCol & "2").Copy
        .Range(c1 & "2:" & c2 & "2").PasteSpecial Paste:=xlPasteFormats
        col = .Range(c1 & "2").Column
        For i = 0 To UBound(nombres)
            .Cells(2, col + i).Value = nombres(i)
        Next i

        ' % Limite Pt (7a columna): formato visual de porcentaje (valor viene 0-100)
        .Range(.Cells(3, col + 6), .Cells(.Rows.Count, col + 6)).NumberFormat = "0.00""%"""

        .Range(c1 & "1:" & c2 & "1").UnMerge
        .Range(refCol & "1").Copy
        .Range(c1 & "1:" & c2 & "1").PasteSpecial Paste:=xlPasteFormats
        .Range(c1 & "1:" & c2 & "1").Merge
        .Range(c1 & "1").Value = "Capas"
    End With
End Sub
