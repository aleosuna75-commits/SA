"""
Pruebas de reducir_xlsx.py y verificar_xlsx.py con libros pequeños hechos a
mano (cubren los casos que encontraron las revisiones).

Uso:
    python3 herramientas/probar_xlsx.py
"""

import os
import re
import subprocess
import sys
import tempfile
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
NS = ('xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
TIPO = "application/vnd.openxmlformats-officedocument.spreadsheetml"
ESTILOS = (f'<styleSheet {NS}><fonts count="1"><font/></fonts><fills count="1"><fill/>'
           '</fills><borders count="1"><border/></borders><cellXfs count="1"><xf/>'
           '</cellXfs></styleSheet>')
fallas = []


def libro(ruta, hojas, textos=(), nombres="", vista='activeTab="0"', extra=(), rels_extra=""):
    """hojas: [(nombre, sheetData)]; extra: [(parte, xml, tipo o None)]."""
    tipos = [f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="{TIPO}.worksheet+xml"/>'
             for i in range(1, len(hojas) + 1)]
    tipos += [f'<Override PartName="/{p}" ContentType="{t}"/>' for p, _, t in extra if t]
    partes = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-'
        'package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/xl/workbook.xml" ContentType="{TIPO}.sheet.main+xml"/>'
        f'<Override PartName="/xl/styles.xml" ContentType="{TIPO}.styles+xml"/>'
        f'<Override PartName="/xl/sharedStrings.xml" ContentType="{TIPO}.sharedStrings+xml"/>'
        + "".join(tipos) + "</Types>",
        "_rels/.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        f'relationships"><Relationship Id="rId1" Type="{REL}/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<workbook {NS}><bookViews><workbookView {vista}/></bookViews><sheets>'
        + "".join(f'<sheet name="{n}" sheetId="{i}" r:id="rId{i}"/>'
                  for i, (n, _) in enumerate(hojas, 1))
        + f"</sheets>{nombres}</workbook>",
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/'
        'package/2006/relationships">'
        + "".join(f'<Relationship Id="rId{i}" Type="{REL}/worksheet" '
                  f'Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(hojas) + 1))
        + f'<Relationship Id="rE" Type="{REL}/styles" Target="styles.xml"/>'
        f'<Relationship Id="rT" Type="{REL}/sharedStrings" Target="sharedStrings.xml"/>'
        + rels_extra + "</Relationships>",
        "xl/styles.xml": ESTILOS,
        "xl/sharedStrings.xml": f'<sst {NS} count="{len(textos)}" uniqueCount="{len(textos)}">'
        + "".join(f"<si><t>{t}</t></si>" for t in textos) + "</sst>",
    }
    for i, (_, datos) in enumerate(hojas, 1):
        partes[f"xl/worksheets/sheet{i}.xml"] = f"<worksheet {NS}><sheetData>{datos}</sheetData></worksheet>"
    for p, xml, _ in extra:
        partes[p] = xml
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for p, xml in partes.items():
            z.writestr(p, xml)


def correr(script, *args):
    r = subprocess.run([sys.executable, os.path.join(AQUI, script), *args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def revisar(nombre, condicion, detalle=""):
    print(("ok   " if condicion else "MAL  ") + nombre)
    if not condicion:
        fallas.append(nombre)
        print("     " + detalle.strip().replace("\n", "\n     ")[-800:])


def reducir_y_verificar(d, nombre, *quitar):
    origen, destino = os.path.join(d, nombre + ".xlsx"), os.path.join(d, nombre + "_r.xlsx")
    args = [a for h in quitar for a in ("--quitar-hoja", h)]
    rc, salida = correr("reducir_xlsx.py", origen, destino, "--rapido", *args)
    if rc:
        return rc, salida, None
    rc, salida2 = correr("verificar_xlsx.py", origen, destino,
                         *[a for h in quitar for a in ("--quitada", h)])
    return rc, salida + salida2, destino


def main():
    d = tempfile.mkdtemp(prefix="probar_xlsx_")
    c = lambda ref, v, extra="": f'<c r="{ref}"{extra}><v>{v}</v></c>'

    # 1. Sin pérdida: saltos de fila y columna, fórmula compartida, 1a fila != 1.
    datos = ('<row r="2">' + c("A2", 1) + c("B2", 2) + c("D2", 4) + '</row>'
             '<row r="3">' + c("A3", 5) + '<c r="B3"><f t="shared" ref="B3:C3" si="0">A3*2</f>'
             '<v>10</v></c><c r="C3"><f t="shared" si="0"/><v>0</v></c>' + c("D3", 7) + '</row>'
             '<row r="5">' + c("A5", 8) + c("B5", 9) + '</row>'
             '<row r="6">' + c("A6", 1) + c("B6", 0, ' t="s"') + '</row>')
    libro(os.path.join(d, "base.xlsx"), [("Datos", datos)], textos=["uno"])
    rc, salida, destino = reducir_y_verificar(d, "base")
    revisar("sin pérdida con saltos y fórmulas compartidas", rc == 0, salida)
    if destino:
        xml = zipfile.ZipFile(destino).read("xl/worksheets/sheet1.xml").decode()
        refs = re.findall(r'<c r="([A-Z]+\d+)"', xml)
        revisar("r se conserva donde hace falta (filas tras salto, D2, fórmulas)",
                refs == ["A2", "B2", "D2", "B3", "C3", "A5", "B5"], str(refs))

    # 2. Comentarios en sheetData: la hoja no se toca.
    libro(os.path.join(d, "coment.xlsx"),
          [("Datos", '<row r="1">' + c("A1", 1) + '<!-- <c r="B1"/> -->' + c("C1", 3) + "</row>")])
    rc, salida, destino = reducir_y_verificar(d, "coment")
    revisar("hoja con comentarios queda igual", rc == 0 and destino and zipfile.ZipFile(destino).read(
        "xl/worksheets/sheet1.xml") == zipfile.ZipFile(os.path.join(d, "coment.xlsx")).read(
        "xl/worksheets/sheet1.xml"), salida)

    # 3. Casos en que quitar una hoja debe negarse.
    formula = lambda f: '<row r="1"><c r="A1"><f>' + f + "</f><v>0</v></c></row>"
    uno = '<row r="1">' + c("A1", 1) + "</row>"
    negar = {
        "referencia directa": ([("Datos", formula("Borrar!A1*2")), ("Borrar", uno)], "Borrar", {}),
        "nombre con apóstrofo": ([("Datos", formula("'O''Brien'!A1")), ("O&apos;Brien", uno)],
                                 "O'Brien", {}),
        "referencia 3D": ([("H1", uno), ("Borrar", uno), ("H3", uno),
                           ("Suma", formula("SUM(H1:H3!A1)"))], "Borrar", {}),
        "nombre definido global": ([("Datos", uno), ("Borrar", uno)], "Borrar",
                                   {"nombres": '<definedNames><definedName name="x">'
                                    "Borrar!$A$1</definedName></definedNames>"}),
        "hoja activa": ([("Borrar", uno), ("Datos", uno)], "Borrar", {"vista": ""}),
        "origen de tabla dinámica": ([("Datos", uno), ("Borrar", uno)], "Borrar", {
            "extra": [("xl/pivotCache/pivotCacheDefinition1.xml",
                       f'<pivotCacheDefinition {NS}><cacheSource type="worksheet">'
                       '<worksheetSource ref="A1:A2" sheet="Borrar"/></cacheSource>'
                       "</pivotCacheDefinition>", f"{TIPO}.pivotCacheDefinition+xml")],
            "rels_extra": f'<Relationship Id="rP" Type="{REL}/pivotCacheDefinition" '
                          'Target="pivotCache/pivotCacheDefinition1.xml"/>'}),
    }
    for caso, (hojas, quitar, opciones) in negar.items():
        libro(os.path.join(d, "negar.xlsx"), hojas, **opciones)
        rc, salida = correr("reducir_xlsx.py", os.path.join(d, "negar.xlsx"),
                            os.path.join(d, "negar_r.xlsx"), "--rapido", "--quitar-hoja", quitar)
        revisar(f"se niega a quitar la hoja: {caso}", rc != 0, salida)

    # 4. Tabla de la hoja quitada usada en otra hoja.
    libro(os.path.join(d, "tabla.xlsx"), [("Datos", formula("SUM(Tabla1[Monto])")), ("Borrar", uno)],
          extra=[("xl/tables/table1.xml", f'<table {NS} id="1" name="Tabla1" displayName="Tabla1" '
                  'ref="A1:A2"/>', f"{TIPO}.table+xml"),
                 ("xl/worksheets/_rels/sheet2.xml.rels", '<Relationships xmlns="http://schemas.'
                  f'openxmlformats.org/package/2006/relationships"><Relationship Id="rT1" '
                  f'Type="{REL}/table" Target="../tables/table1.xml"/></Relationships>', None)])
    rc, salida = correr("reducir_xlsx.py", os.path.join(d, "tabla.xlsx"),
                        os.path.join(d, "tabla_r.xlsx"), "--rapido", "--quitar-hoja", "Borrar")
    revisar("se niega a quitar la hoja: referencia a su tabla", rc != 0, salida)

    # 5. Quitar una hoja bien: calcChain, nombre local vacío, t='s', textos podados.
    libro(os.path.join(d, "quitar.xlsx"),
          [("Datos", "<row r=\"1\"><c r=\"A1\" t='s'><v>2</v></c>" + c("B1", 1) + "</row>"),
           ("Borrar", '<row r="1">' + c("A1", 0, ' t="s"') + c("B1", 1, ' t="s"') + "</row>")],
          textos=["solo borrar", "otro de borrar", "de datos"],
          nombres='<definedNames><definedName name="Vacio" localSheetId="1"/>'
                  '<definedName name="Global">Datos!$A$1</definedName></definedNames>',
          extra=[("xl/calcChain.xml", f'<calcChain {NS}><c r="A1" i="2"/></calcChain>',
                  f"{TIPO}.calcChain+xml")],
          rels_extra=f'<Relationship Id="rC" Type="{REL}/calcChain" Target="calcChain.xml"/>')
    rc, salida, destino = reducir_y_verificar(d, "quitar", "Borrar")
    revisar("quita una hoja y verifica", rc == 0, salida)
    if destino:
        z = zipfile.ZipFile(destino)
        libro_xml = z.read("xl/workbook.xml").decode()
        revisar("calcChain quitado", "xl/calcChain.xml" not in z.namelist()
                and b"calcChain" not in z.read("[Content_Types].xml")
                and b"calcChain" not in z.read("xl/_rels/workbook.xml.rels"))
        revisar("nombre local quitado y global conservado",
                "Vacio" not in libro_xml and "Global" in libro_xml, libro_xml)
        sst = z.read("xl/sharedStrings.xml").decode()
        revisar("textos podados y celda t='s' renumerada",
                "de datos" in sst and "borrar" not in sst
                and "<v>0</v>" in z.read("xl/worksheets/sheet1.xml").decode(), sst)

        # 6. El verificador rechaza un paquete roto (falta styles.xml).
        roto = os.path.join(d, "roto.xlsx")
        with zipfile.ZipFile(destino) as zin, zipfile.ZipFile(roto, "w") as zout:
            for n in zin.namelist():
                if n != "xl/styles.xml":
                    zout.writestr(zin.getinfo(n), zin.read(n))
        rc, salida = correr("verificar_xlsx.py", os.path.join(d, "quitar.xlsx"), roto,
                            "--quitada", "Borrar")
        revisar("el verificador rechaza un paquete al que le falta una parte", rc != 0, salida)

    print(f"\n{len(fallas)} fallas" if fallas else "\nTodas las pruebas pasaron")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
