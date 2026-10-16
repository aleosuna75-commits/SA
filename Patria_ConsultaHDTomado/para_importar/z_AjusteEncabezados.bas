Attribute VB_Name = "z_AjusteEncabezados"
Option Explicit

' Ajuste de UNA SOLA VEZ, despues de importar las macros sin cuadro de
' retrocesion. Borra las columnas de encabezado "Retrocesión" (y en NoProp
' tambien las de "Capas") para que los encabezados de las filas 1-2 queden
' alineados con lo que ahora trae la consulta. Valida los encabezados antes de
' borrar y, si se corre otra vez, no hace nada.

Sub AjustaEncabezadosSinRetro()
    Dim msg As String
    Application.ScreenUpdating = False

    ' True = borra desde "Retrocesión" hasta la ultima columna de la hoja
    ' (en Prop quita tambien una columna vieja que la macro ya no llenaba,
    ' y en NoProp quita tambien las capas). False = solo las 7 de retro.
    msg = msg & QuitaRetro("Prop", True)
    msg = msg & QuitaRetro("NoProp", True)
    msg = msg & QuitaRetro("NoProp_sbr", False)
    msg = msg & QuitaRetro("FacultativoOFD", True)
    msg = msg & QuitaRetro("FacultativoOFF", True)
    msg = msg & QuitaRetro("FacultativoOFV", True)
    msg = msg & QuitaRetro("FacultativoOFVG", True)

    Application.ScreenUpdating = True
    MsgBox msg & vbLf & "Ahora corre la consulta para refrescar los datos.", vbInformation
End Sub

Private Function QuitaRetro(ByVal hoja As String, ByVal hastaElFinal As Boolean) As String
    Dim ws As Worksheet, c As Variant, ultCol As Long, j As Long, v As String
    Set ws = ThisWorkbook.Worksheets(hoja)

    c = Application.Match("Retrocesión", ws.Rows(1), 0)
    If IsError(c) Then
        QuitaRetro = hoja & ": ya estaba ajustada, no se modifico." & vbLf
        Exit Function
    End If
    If ws.Cells(2, c).Value <> "Corredor" Or ws.Cells(2, c + 1).Value <> "No.Contrato" Then
        QuitaRetro = hoja & ": los encabezados no son los esperados, NO se modifico." & vbLf
        Exit Function
    End If

    If hastaElFinal Then
        ultCol = ws.Cells.Find("*", SearchOrder:=xlByColumns, SearchDirection:=xlPrevious).Column
        ' A la derecha de retro solo se aceptan columnas sin titulo o el bloque "Capas"
        For j = c + 1 To ultCol
            v = CStr(ws.Cells(1, j).Value)
            If v <> "" And v <> "Capas" Then
                QuitaRetro = hoja & ": hay columnas no esperadas a la derecha de Retrocesión (" & v & "), NO se modifico." & vbLf
                Exit Function
            End If
        Next j
    Else
        ultCol = c + 6
    End If

    ws.Range(ws.Cells(1, c), ws.Cells(1, ultCol)).EntireColumn.Delete
    QuitaRetro = hoja & ": se quitaron " & (ultCol - c + 1) & " columnas." & vbLf
End Function

' Revision despues de correr la consulta. Por hoja reporta:
'  - filas identicas repetidas (todas las columnas iguales), que solo pueden
'    venir de un cruce de tablas que duplica;
'  - en Prop y NoProp, contratos repetidos (corredor, compañía, contrato y año
'    con sus versiones), que deben ser 0 porque ahi va una fila por contrato.
' NoProp_sbr no se revisa por contrato: es de detalle (subramo y capa).
Sub VerificaRepetidos()
    Dim hojas As Variant, h As Variant, msg As String
    hojas = Array("Prop", "NoProp", "NoProp_sbr", "FacultativoOFD", "FacultativoOFF", "FacultativoOFV", "FacultativoOFVG")
    Application.ScreenUpdating = False
    For Each h In hojas
        msg = msg & RevisaHoja(ThisWorkbook.Worksheets(h), (h = "Prop" Or h = "NoProp")) & vbLf
    Next h
    Application.ScreenUpdating = True
    MsgBox msg, vbInformation, "Revision de repetidos"
End Sub

Private Function RevisaHoja(ws As Worksheet, ByVal porContrato As Boolean) As String
    Dim ultFila As Long, ultCol As Long, datos As Variant, i As Long, j As Long
    Dim filas As Object, llaves As Object, s As String, k As String
    Dim repFila As Long, repLlave As Long

    ultFila = ws.Cells(ws.Rows.Count, 2).End(xlUp).Row
    If ultFila < 3 Then
        RevisaHoja = ws.Name & ": sin datos"
        Exit Function
    End If
    ultCol = ws.Cells(2, ws.Columns.Count).End(xlToLeft).Column
    datos = ws.Range(ws.Cells(3, 2), ws.Cells(ultFila, ultCol)).Value

    Set filas = CreateObject("Scripting.Dictionary")
    Set llaves = CreateObject("Scripting.Dictionary")
    For i = 1 To UBound(datos, 1)
        s = ""
        For j = 1 To UBound(datos, 2)
            If IsError(datos(i, j)) Then s = s & "|#ERR" Else s = s & "|" & CStr(datos(i, j))
        Next j
        If filas.Exists(s) Then repFila = repFila + 1 Else filas.Add s, True
        If porContrato Then
            ' B,C,E,F,H,I = cCOR_Id, cCOR_Version, cCIA_Id, cCIA_Version, NoContr, AnioVig
            k = CStr(datos(i, 1)) & "|" & datos(i, 2) & "|" & datos(i, 4) & "|" & datos(i, 5) & "|" & datos(i, 7) & "|" & datos(i, 8)
            If llaves.Exists(k) Then repLlave = repLlave + 1 Else llaves.Add k, True
        End If
    Next i

    RevisaHoja = ws.Name & ": " & UBound(datos, 1) & " filas, " & repFila & " filas identicas repetidas"
    If porContrato Then RevisaHoja = RevisaHoja & ", " & repLlave & " contratos repetidos"
End Function
