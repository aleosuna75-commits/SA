Option Explicit
' Construye la cadena de conexion usando el usuario y contrasena capturados
' en la hoja CONTROL (celdas con nombre UsuarioSIREC / PasswordSIREC).
Public Function CadenaConexion() As String
    Dim u As String, p As String
    u = Trim(CStr(Worksheets("CONTROL").Range("UsuarioSIREC").Value))
    p = Trim(CStr(Worksheets("CONTROL").Range("PasswordSIREC").Value))
    CadenaConexion = "Provider=SQLOLEDB;Data Source=adsPeru05;User Id=" & u & ";Password=" & p & ";Initial Catalog=pDBSirec2;"
End Function
