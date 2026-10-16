Option Explicit

' Arma un libro nuevo con el formato de la base que se entrego a PWC
' (ConsultaHDTomado_PWC): mismas hojas, mismas columnas y mismo orden.
' Toma los datos ya consultados, asi que primero hay que correr la consulta.
' Las columnas se buscan por el nombre de campo de la fila 2 de cada hoja, por
' lo que no dependen de la posicion de las columnas en las hojas de consulta.

Sub GeneraBasePWC()
    Dim hojas As Variant, campos As Variant, faltan As String, i As Long
    Dim wbN As Workbook

    hojas = Array("Prop", "NoProp", "FacultativoOFD", "FacultativoOFF", "FacultativoOFVG")
    campos = Array(Campos_Prop(), Campos_NoProp(), Campos_FacultativoOFD(), _
                   Campos_FacultativoOFF(), Campos_FacultativoOFVG())

    ' Valida antes de crear nada que todos los campos existan
    For i = 0 To UBound(hojas)
        faltan = faltan & CamposFaltantes(ThisWorkbook.Worksheets(hojas(i)), campos(i))
    Next i
    If faltan <> "" Then
        MsgBox "No se genero la base PWC. No se encontraron estos campos en la fila 2:" & vbLf & faltan, vbExclamation
        Exit Sub
    End If

    Application.ScreenUpdating = False
    Set wbN = Workbooks.Add(xlWBATWorksheet)
    For i = 0 To UBound(hojas)
        CopiaHojaPWC ThisWorkbook.Worksheets(hojas(i)), wbN, campos(i), i = 0
    Next i
    wbN.Worksheets(1).Activate
    Application.ScreenUpdating = True

    MsgBox "Base PWC generada en un libro nuevo. Revisala y guardala con el nombre que corresponda."
End Sub

Private Function CamposFaltantes(ws As Worksheet, ByVal lista As String) As String
    Dim par As Variant, campo As String
    For Each par In Split(lista, ";")
        If par <> "" Then
            campo = Split(par, "|")(1)
            If IsError(Application.Match(campo, ws.Rows(2), 0)) Then
                CamposFaltantes = CamposFaltantes & ws.Name & ": " & campo & vbLf
            End If
        End If
    Next par
End Function

Private Sub CopiaHojaPWC(wsO As Worksheet, wbN As Workbook, ByVal lista As String, ByVal esPrimera As Boolean)
    Dim wsD As Worksheet, par As Variant, partes() As String
    Dim col As Long, colO As Long, ultFila As Long

    If esPrimera Then
        Set wsD = wbN.Worksheets(1)
    Else
        Set wsD = wbN.Worksheets.Add(After:=wbN.Worksheets(wbN.Worksheets.Count))
    End If
    wsD.Name = wsO.Name

    ultFila = wsO.Cells(wsO.Rows.Count, 2).End(xlUp).Row
    For Each par In Split(lista, ";")
        If par <> "" Then
            partes = Split(par, "|")
            col = col + 1
            colO = Application.Match(partes(1), wsO.Rows(2), 0)
            wsD.Cells(1, col).Value = partes(0)
            wsD.Cells(2, col).Value = partes(1)
            If ultFila >= 3 Then
                wsD.Range(wsD.Cells(3, col), wsD.Cells(ultFila, col)).Value = _
                    wsO.Range(wsO.Cells(3, colO), wsO.Cells(ultFila, colO)).Value
                wsD.Columns(col).NumberFormat = wsO.Cells(3, colO).NumberFormat
            End If
        End If
    Next par
    wsD.Range(wsD.Cells(1, 1), wsD.Cells(2, col)).Font.Bold = True
End Sub

Private Function Campos_Prop() As String
    Dim c As String
    c = c & "CORREDOR|cCOR_Id;CORREDOR|Nombre Corredor;COMPAÑÍA|cCIA_Id;COMPAÑÍA|Nombre Compañía;"
    c = c & "Número Contrato|aHTP_NoContr;Año Vigencia|aHTP_AnioVig;Tipo de Contrato|cTCT_Id;Tipo de Contrato|Tipo de Contrato;"
    c = c & "Moneda|cMON_Id;Moneda|Nombre Moneda;Referencia|aHTP_RefOrig;Monto Limite de Responsabilidad|aHTP_MntLimRes;"
    c = c & "Porcentaje Limite de Responsabilidad Patria|aHTP_PrcLimResPt;Monto Limite de Responsabilidad Patria|aHTP_MntLimResPt;Monto Prima Estimada 100%|aHTP_CienMntPriEst;Monto Prima Estimada Patria100%|aHTP_CienMntPriEstPt;"
    c = c & "Comisión Patria 100%|aHTP_CienComisionPt;Reserva Prima de Patria 100%|aHTP_CienRvaPriPt;Comisión Escalonada|aHTP_SobComision;Comisión sobre Utilidad|aHTP_ComSobUtilidades;"
    c = c & "Porcetanje de Corretaje|aHTP_PrcCorretaje;Porcentaje Impuesto sobre Prima|aHTP_PrcImpSobPrima;Porcentaje Impuesto sobre Intereses|aHTP_PrcImpSobInt;Cuentas Rendidas|cPRD_Id;"
    c = c & "Dentro de|aHTP_DesdeDias;A pagar en|aHTP_PagenDias;Forma de Registro|cFRE_Id;Fecha Inicio de Vigencia|aHTP_FecIniPerCub;"
    c = c & "Fecha Fin de Vigencia|aHTP_FecFinPerCub;Fecha de Captura|aHTP_FecCaptura;Fecha de Expedición|aHTP_FecExpedicion;Utilidades|aHTP_Utilidades;"
    c = c & "Gastos del Reasegurador|aHTP_Sobre;Comisión Escalonada|aHTP_EsComEscalonada;Comisión Escalonada Siniestralidad Max|aHTP_comEscalonadaStdlMax;Comisión Escalonada Máxima|aHTP_comEscalonadaMax;"
    c = c & "Comisión Escalonada Siniestralidad Min|aHTP_comEscalonadaStdlMin;Escalonada|aHTP_escalonada;Gastos del Reasegurador|aHTP_ProcentajeGR;Extinción|aHTP_Extincion;"
    Campos_Prop = c
End Function

Private Function Campos_NoProp() As String
    Dim c As String
    c = c & "CORREDOR|cCOR_Id;CORREDOR|cCOR_Version;COMPAÑÍA|cCIA_Id;COMPAÑÍA|Nombre Compañía;"
    c = c & "Número Contrato|aHTNP_NoContr;Año Vigencia|aHTNP_AnioVig;Territorio|cTRE_Id;Tipo de Contrato|cTCT_Id;"
    c = c & "Tipo de Contrato|Tipo de Contrato;Moneda|cMON_Id;Moneda|Nombre Moneda;Referencia|aHTNP_RefOrig;"
    c = c & "Monto Limite de Responsabilidad|aHTNP_MntLimRes;Porcentaje Limite de Responsabilidad Patria|aHTNP_MntLimResPt;PMD|aHTNP_MntPriMinDep;PMD Patria|aHTNP_MntPriMinDepPt;"
    c = c & "Monto Prima Estimada|aHTNP_MntPriEst;Monto Prima Estimada Patria|aHTNP_MntPriEstPt;Prima Protegida Estimada|aHTNP_MntPriPro;Monto Impuestos|aHTNP_MntImpuesto;"
    c = c & "Monto Corretaje|aHTNP_MntCorretaje;Cuentas Rendidas|cPRD_Id;Garantía|aHTNP_Garantia;Fecha Inicio de Vigencia|aHTNP_FecIniPerCub;"
    c = c & "Fecha Fin de Vigencia|aHTNP_FecFinPerCub;Fecha Original|aHTNP_FecOriginal;Fecha de Expedición|aHTNP_FecExpedicion;Fecha de Captura|aHTNP_FecCaptura;"
    Campos_NoProp = c
End Function

Private Function Campos_FacultativoOFD() As String
    Dim c As String
    c = c & "Número Contrato|aOFD_NoContr;Año Vigencia|aOFD_AnioVig;Número de Oferta|aOFD_NoOferta;Número de Endoso|aOFD_NoEndoso;"
    c = c & "Número de Aceptación|aOFD_NoAcep;CORREDOR|cCOR_Id;CORREDOR|Nombre Corredor;COMPAÑÍA|cCIA_Id;"
    c = c & "COMPAÑÍA|Nombre Compañía;Territorio|cTER_Id;Tipo de Reaseguro|cTRE_Id;Tipo de Contrato|cTCT_Id;"
    c = c & "Tipo de Contrato|Tipo de Contrato;Moneda|cMON_Id;Moneda|Nombre Moneda;Giro|cGRM_Id;"
    c = c & "Giro|Giro;Fecha Oferta|aOFD_FecOferta;Fecha Captura|aOFD_FecCaptura;Endoso|cEND_Id;"
    c = c & "Asegurado|cAMO_Id;|Nombre Asegurado;Fecha Inicio de Vigencia|aOFD_FecIniVig;Fecha Fin de Vigencia|aOFD_FecFinVig;"
    c = c & "|Nombre País;Bien Asegurado|aOFD_BienAse;Renueva Oferta|aOFD_Renueva;Monto Suma Asegurada|aOFD_MntSumAse;"
    c = c & "Monto Prima de Riesgo|aOFD_MntPriRgo;Porcentaje Aceptación Patria|aOFD_PrcAceptPt;Monto Aceptación Patria|aOFD_MntAceptPt;Monto EPI Patria por Capa|aOFD_MntEpiPtCapa;"
    c = c & "Monto Cobertura por Capa|aOFD_MntCobCapa;Monto Suma Asegurada MyT|aOFD_MntSumAseMyT;Porcentaje Cuota|aOFD_PrcCuota;Porcentaje Reserva Primas|aOFD_PrcRvaPrimas;"
    c = c & "Monto Prima Estimada|aOFD_MntPriEst;Monto Prima Estimada Patria|aOFD_MntPriEstPt;Comision|aOFD_Comision;Intereses sobre Reserva|aOFD_PrcIntRes;"
    c = c & "Porcentaje Corretaje|aOFD_PrcCorretaje;Porcentaje Impuesto sobre Primas|aOFD_PrcImpPrimas;Impuestos sobre Interés|aOFD_PrcImpInter;Estado de Cuenta|aOFD_EdoCta;"
    c = c & "Situación|cSTC_Id;"
    Campos_FacultativoOFD = c
End Function

Private Function Campos_FacultativoOFF() As String
    Dim c As String
    c = c & "Número Contrato|aOFF_Contrato;Territorio|cTER_Id;Tipo de Reaseguro|cTRE_Id;Año Vigencia|aOFF_Año;"
    c = c & "Número de Oferta|aOFF_NumOferta;Número de Endoso|aOFF_NumEndoso;CORREDOR|cCOR_Id;CORREDOR|Nombre Corredor;"
    c = c & "COMPAÑÍA|cCIA_Id;COMPAÑÍA|Nombre Compañía;Número Aceptación|aOFF_NumAcepta;Moneda|cMON_Id;"
    c = c & "Moneda|Nombre Moneda;Giro|cGRM_Id;Giro|Giro;Número de Póliza|aOFF_NumPoliza;"
    c = c & "|Nombre País;Endoso|cEND_Id;Fecha Oferta|aOFF_FecOferta;Fecha Captura|aOFF_FecCaptura;"
    c = c & "Afianzado|cADO_Id;Afianzado|Nombre Afianzado;Fecha Inicio de Vigencia|aOFF_FecVigIni;Fecha Fin de Vigencia|aOFF_FecVigFin;"
    c = c & "Suma Afianzada|aOFF_SumaAfi;Monto Patria|aOFF_MontoPt;EPI 100%|aOFF_EPI100;EPI Patria|aOFF_EPIPt;"
    c = c & "Comisiones|aOFF_Comision;Cuota|aOFF_Cuota;Corretaje|aOFF_Corretaje;Reserva Primas|aOFF_RvaPrimas;"
    c = c & "Reserva Intereses|aOFF_RvaIntereses;Impuesto sobre Prima|aOFF_ImpPrimas;Impuestos sobre Interés|aOFF_ImpInteres;Estado de Cuenta|aOFF_EdoCta;"
    c = c & "Situación|cSTC_Id;"
    Campos_FacultativoOFF = c
End Function

Private Function Campos_FacultativoOFVG() As String
    Dim c As String
    c = c & "Número Contrato|aOFVG_NumContr;Territorio|cTER_Id;Tipo de Reaseguro|cTRE_Id;Año Vigencia|aOFVG_AñoVig;"
    c = c & "Número de Oferta|aOFVG_NumOfer;Número de Endoso|aOFVG_NumEnd;Número Aceptación|aOFVG_NumAcept;CORREDOR|cCOR_Id;"
    c = c & "CORREDOR|Nombre Corredor;COMPAÑÍA|cCIA_Id;COMPAÑÍA|Nombre Compañía;Moneda|cMON_Id;"
    c = c & "Moneda|Nombre Moneda;Giro|cGRM_Id;Giro|Giro;Endoso Vida|cENDOFV_Id;"
    c = c & "Fecha Oferta|aOFVG_FecOfer;Fecha Captura|aOFVG_FecCaptura;Monto Máximo|cOFVG_MntMax;Monto Acumulado Máximo|cOFVG_AcumMax;"
    c = c & "SAMI|cOFVG_SAMI;Monto Promedio|cOFVG_MntProm;Prima al 100%|cOFVG_PrimaCien;Dividendo|cOFVG_Div;"
    c = c & "Comisión Directa|cOFVG_ComDto;Deductibles Totales|cOFVG_DeducTot;Número de Asegurado|aOFVG_NumAseg;Edad Promedio|aOFVG_EdadProm;"
    c = c & "Edad Máxima|aOFVG_EdadMax;Número de Certificado|aOFVG_NumCert;Comision de Reaseguro|aOFVG_ComReas;Porcentaje Reserva Primas|aOFVG_PrcRvaPrimas;"
    c = c & "Porcentaje Intereses|aOFVG_PrcInts;Porcentaje Corretaje|aOFVG_PrcCorje;Porcentaje Impuesto Sobre Prima|aOFVG_PrcImptoPrim;Porcentaje Impuesto sobre Intereses|aOFVG_PrcImptoInts;"
    c = c & "Fecha Inicio de Vigencia|aOFVG_FecIniVig;Fecha Fin de Vigencia|aOFVG_FecFinVig;Situación|cSTC_Id;"
    Campos_FacultativoOFVG = c
End Function
