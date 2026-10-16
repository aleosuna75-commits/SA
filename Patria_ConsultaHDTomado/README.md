# ConsultaHDTomado: quitar el cuadro de retrocesión (contratos repetidos)

Solicitud de Eduardo (15/10/2026): en la base se repiten contratos y el cuadro de
retrocesión parece ser la causa. Se usa como referencia la base que se envió a PWC
el año pasado (`ConsultaHDTomado_PWC.xlsx`), que trae una fila por contrato.

## Diagnóstico (con los datos del archivo `ConsultaHDTomado_202610.xlsm`)

| Hoja | Filas hoy | Contratos/ofertas reales | Causa de la repetición |
|---|---:|---:|---|
| Prop | 3,190 | 959 | Cuadro de retro (T12) y un cruce a `rPCRXHTP` (T17) que no aportaba columnas y repetía por ramo/subramo. Además el cruce de retro tenía un error (`T1.cCOR_Id=T2.cCOR_Id` en vez de `T12`). |
| NoProp | 9,935 | 774 | Cuadro de retro × capas. |
| NoProp_sbr | 44,523 | ~7,581 | Cuadro de retro (la hoja es de detalle por subramo y capa, eso se conserva). |
| FacultativoOFD | 16,632 | ~2,322 | Cuadro de retro. |
| FacultativoOFF | 302 | 224 | Cuadro de retro. |
| FacultativoOFV | 2,586 | ~993 | Cuadro de retro, y corredor/compañía cruzados sin versión del catálogo. |
| FacultativoOFVG | 70 | ~44 | Igual que OFV. |

La columna de "contratos/ofertas reales" se obtuvo quitando de los datos actuales
las columnas de retro y quedándose con las filas distintas. Al refrescar con la
macro nueva deben salir cifras iguales o muy parecidas (cambian si cambió la base).

## Qué cambió en las macros

Todas las tablas que se quitaron eran `LEFT JOIN` cuyas columnas ya no se piden,
así que **no se pierde ningún contrato**: cada consulta regresa exactamente los
registros de su tabla principal (`aHTP`, `aHTNP`, `aOFD`, `aOFF`, `aOFV`, `aOFVG`)
con el mismo filtro de fechas de siempre. Las columnas que quedan conservan su
posición y nombre; solo desaparecen las del bloque "Retrocesión".

- **Prop, NoProp, NoProp_sbr, Fac_Daños, Fac_Fianzas, Fac_VidaI, Fac_VidaG**: sin
  cuadro de retrocesión (`rCRHD_CuadroRetroHD` / `rCROF_CuadroRetroOF` y las tablas
  de contrato cedido `aHCP`, `aHCNP`, `aHCF`).
- **Prop**: también sin `cEMP_Empleado` (T16) ni `rPCRXHTP` (T17), que no se
  mostraban.
- **NoProp**: una fila por contrato, sin capas. **NoProp_sbr** conserva el detalle
  de subramos y capas (las capas ahora empiezan en la columna BP).
- **Fac_VidaI y Fac_VidaG**: corredor y compañía se cruzan por id **y versión**,
  igual que en las demás hojas. Se verificó que todas las versiones que usan estas
  ofertas existen en los catálogos, así que ningún nombre queda vacío.
- **Todas las hojas**: se borra el rango completo de datos antes de pegar (antes
  solo hasta CZ, por eso en Prop quedaban datos viejos en la columna DB) y la
  fórmula llave de la columna A se deja exactamente en las filas con datos (antes
  quedaban miles de filas "---" debajo).
- **a_Inicio, NoProp, NoProp_sbr**: se corrigió `zÁñoIni`/`zÁñoFin` (tenían una
  "Á" de más). Con ese error el filtro "Año Suscripción" nunca funcionaba.
- **EncabezadosCapa**: apunta a la nueva posición de las capas en NoProp_sbr.

Módulos nuevos:

- **z_AjusteEncabezados**: `AjustaEncabezadosSinRetro` (se corre una sola vez) y
  `VerificaRepetidos` (revisión después de cada consulta).
- **BasePWC**: `GeneraBasePWC` arma un libro nuevo con las mismas hojas, columnas y
  orden que la base de PWC del año pasado.

`mConexion` y `Módulo5` no se tocan.

## Cómo aplicarlo (una sola vez)

1. Haz una copia de respaldo de `ConsultaHDTomado_202610.xlsm`.
2. Abre el archivo y entra al editor de VBA con `Alt + F11`.
3. Para cada uno de estos módulos: clic derecho → **Quitar …** → **No** (no exportar):
   `a_Inicio`, `Prop`, `NoProp`, `NoProp_sbr`, `Fac_Daños`, `Fac_Fianzas`,
   `Fac_VidaI`, `Fac_VidaG`, `EncabezadosCapa`.
4. **Archivo → Importar archivo…** e importa todos los `.bas` de la carpeta
   `para_importar` (los 9 anteriores más `z_AjusteEncabezados` y `BasePWC`).
5. **Depuración → Compilar VBAProject**. No debe marcar ningún error.
6. Cierra el editor, `Alt + F8` → `AjustaEncabezadosSinRetro` → Ejecutar. Quita
   las columnas de encabezado "Retrocesión" (y "Capas" en NoProp). Revisa antes de
   borrar que los encabezados sean los esperados; si se vuelve a correr no hace nada.
7. Guarda el archivo.

## Uso

1. En la hoja CONTROL ejecuta la consulta con el botón, como siempre.
2. `Alt + F8` → `VerificaRepetidos`. En **Prop** y **NoProp** debe decir
   `0 contratos repetidos`, y en todas las hojas `0 filas identicas repetidas`.
3. Opcional, para el requerimiento: `Alt + F8` → `GeneraBasePWC`. Crea un libro
   nuevo con el formato de la base de PWC; revísalo y guárdalo.

## Archivos

- `para_importar/`: módulos listos para importar en Excel (Windows-1252, CRLF).
- `macros/`: los mismos módulos en UTF-8, para revisar cambios.
- `macros_originales/`: el código tal como estaba antes del cambio.
