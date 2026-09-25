"""
Comprueba que dos .xlsx tienen exactamente el mismo contenido.

- Toda parte del paquete que no es hoja debe ser idéntica byte por byte,
  salvo las imágenes PNG, que deben tener exactamente los mismos píxeles.
- En cada hoja, lo que está fuera de <sheetData> debe ser idéntico, y dentro
  cada fila y cada celda debe coincidir en posición, atributos (salvo r),
  fórmula y valor. La posición de las celdas sin r se calcula como indica
  el estándar: columna de la celda anterior + 1. Las celdas de texto
  compartido se comparan por el texto, no por su número de índice.
- El zip debe ser coherente (encabezados locales = directorio central) y
  guardar las partes en el mismo orden físico que el original.
- Compatibilidad con lectores conocidos: la reducción no puede dejar sin r
  celdas con fórmula compartida (openpyxl) ni celdas en filas cuyo número no
  es el de la fila anterior + 1 (WPS).

- El paquete debe ser coherente: todo XML bien formado, todo destino de
  relación existe y toda parte tiene tipo de contenido.

Con --quitada NOMBRE se acepta que esa hoja ya no esté. Se calcula desde el
original qué partes le pertenecían sólo a ella (más calcChain) y se exige que
falten exactamente ésas; los nombres definidos, la hoja activa, las
relaciones, los tipos de contenido y los títulos de docProps/app.xml deben
ser los del original menos la hoja. Los cambios se muestran para revisarlos.

Uso:
    python3 herramientas/verificar_xlsx.py ORIGINAL.xlsx REDUCIDO.xlsx
        [--quitada NOMBRE ...]
"""

import argparse
import difflib
import html
import io
import posixpath
import re
import struct
import sys
import zipfile
import zlib

from lxml import etree

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
VT = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
TEXTOS = "xl/sharedStrings.xml"
AJUSTADAS = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels",
             "[Content_Types].xml", "docProps/app.xml", TEXTOS}


def columna(letras):
    n = 0
    for ch in letras:
        n = n * 26 + (ord(ch) - 64)
    return n


def resolver(parte, destino):
    if destino.startswith("/"):
        return posixpath.normpath(destino[1:])
    return posixpath.normpath(posixpath.join(posixpath.dirname(parte), destino))


def ruta_rels(parte):
    return posixpath.join(posixpath.dirname(parte), "_rels",
                          posixpath.basename(parte) + ".rels")


def relaciones(partes, parte):
    """[(Id, Type, destino)] de una parte; destino None si es externo."""
    raiz = etree.fromstring(partes[ruta_rels(parte)]) if ruta_rels(parte) in partes else []
    return [(r.get("Id"), r.get("Type"),
             None if r.get("TargetMode") == "External" else resolver(parte, r.get("Target")))
            for r in raiz]


def hojas(partes):
    """{nombre de hoja: parte} en el orden del libro."""
    rels = {i: d for i, _, d in relaciones(partes, "xl/workbook.xml")}
    libro = etree.fromstring(partes["xl/workbook.xml"])
    return {h.get("name"): rels[h.get(f"{{{R}}}id")] for h in libro.iter(f"{NS}sheet")}


def estructura(partes):
    """Problemas de coherencia del paquete: XML, relaciones y tipos."""
    problemas = []
    tipos = etree.fromstring(partes["[Content_Types].xml"])
    por_ext = {d.get("Extension").lower() for d in tipos.iter(f"{{{CT}}}Default")}
    por_parte = {o.get("PartName").lower() for o in tipos.iter(f"{{{CT}}}Override")}
    for n, datos in partes.items():
        if n.endswith("/"):
            continue
        if n.endswith((".xml", ".rels", ".vml")):
            try:
                etree.fromstring(datos, etree.XMLParser(huge_tree=True))
            except etree.XMLSyntaxError as e:
                problemas.append(f"{n}: XML mal formado ({e})")
                continue
        if ("/" + n).lower() not in por_parte and n.rsplit(".", 1)[-1].lower() not in por_ext:
            problemas.append(f"{n}: sin tipo de contenido")
        if n.endswith(".rels"):
            origen = posixpath.dirname(posixpath.dirname(n))
            origen = posixpath.join(origen, posixpath.basename(n)[:-5]) if origen else ""
            for _, _, d in relaciones(partes, origen):
                if d is not None and d not in partes:
                    problemas.append(f"{n}: apunta a {d}, que no existe")
    for o in por_parte:
        if o[1:] not in {n.lower() for n in partes}:
            problemas.append(f"[Content_Types].xml: tipo para {o}, que no existe")
    return problemas


def propias(partes, hoja):
    """Partes alcanzables sólo desde `hoja` (incluida), con sus .rels."""
    quitar, cambio = {hoja}, True
    while cambio:
        cambio = False
        vivos = [""] + [p for p in partes if p not in quitar and not p.endswith("/")]
        usados = {d for p in vivos for _, _, d in relaciones(partes, p)}
        for p in list(quitar):
            for _, _, d in relaciones(partes, p):
                if d in partes and d not in quitar and d not in usados:
                    quitar.add(d)
                    cambio = True
    return quitar | {ruta_rels(p) for p in quitar if ruta_rels(p) in partes}


def libro_semantico(partes):
    """Hojas, nombres definidos y vista del libro, con índices por nombre."""
    libro = etree.fromstring(partes["xl/workbook.xml"])
    nombres = [h.get("name") for h in libro.iter(f"{NS}sheet")]
    hojas_ = [(h.get("name"), h.get("sheetId"), h.get("state")) for h in libro.iter(f"{NS}sheet")]
    definidos = sorted(
        (d.get("name"), nombres[int(d.get("localSheetId"))] if d.get("localSheetId") else None,
         tuple(sorted((k, v) for k, v in d.attrib.items() if k not in ("name", "localSheetId"))),
         d.text) for d in libro.iter(f"{NS}definedName"))
    hoja = lambda i: nombres[int(i)] if int(i) < len(nombres) else f"#{i} (no existe)"
    vistas = [(hoja(v.get("activeTab", 0)), hoja(v.get("firstSheet", 0)))
              for v in libro.iter(f"{NS}workbookView")]
    return hojas_, definidos, vistas


def titulos_app(partes):
    if "docProps/app.xml" not in partes:
        return None
    raiz = etree.fromstring(partes["docProps/app.xml"])
    titulos = [t.text for t in raiz.iter(f"{{{VT}}}lpstr")
               if t.getparent().getparent() is not None
               and t.getparent().getparent().tag.endswith("TitlesOfParts")]
    pares = [v.text for v in raiz.iter(f"{{{VT}}}i4")]
    return titulos[:int(pares[0])] if pares else titulos


def revisar_quitadas(pa, pb, quitadas):
    """Compara el paquete reducido con el original menos las hojas quitadas."""
    problemas = []
    hojas_a = hojas(pa)
    esperado = dict(pa)
    for nombre in quitadas:
        if nombre not in hojas_a:
            return [f"el original no tiene la hoja {nombre!r}"]
        propias_ = propias(esperado, hojas_a[nombre])
        cadena = [d for _, t, d in relaciones(esperado, "xl/workbook.xml")
                  if t.endswith("/calcChain")]
        for p in propias_ | ({cadena[0]} if cadena else set()):
            esperado.pop(p, None)
    faltan = set(pa) - set(pb)
    if faltan != set(pa) - set(esperado):
        problemas.append(f"partes quitadas {sorted(faltan)}; se esperaban "
                         f"{sorted(set(pa) - set(esperado))}")
    hojas_ea, def_a, vis_a = libro_semantico(pa)
    hojas_eb, def_b, vis_b = libro_semantico(pb)
    if [h for h in hojas_ea if h[0] not in quitadas] != hojas_eb:
        problemas.append("xl/workbook.xml: la lista de hojas no es la original menos la quitada")
    if [d for d in def_a if d[1] not in quitadas] != def_b:
        problemas.append("xl/workbook.xml: los nombres definidos cambiaron")
    if vis_a != vis_b:
        problemas.append(f"xl/workbook.xml: la hoja activa/primera cambió {vis_a} -> {vis_b}")
    rels_a = {(t, d) for _, t, d in relaciones(pa, "xl/workbook.xml")
              if d is None or d in esperado}
    rels_b = {(t, d) for _, t, d in relaciones(pb, "xl/workbook.xml")}
    if rels_a != rels_b:
        problemas.append(f"xl/_rels/workbook.xml.rels: {rels_a ^ rels_b}")
    tipos = lambda p: {(e.tag, tuple(sorted(e.attrib.items())))
                       for e in etree.fromstring(p["[Content_Types].xml"])}
    esperados = {t for t in tipos(pa) if dict(t[1]).get("PartName", "/")[1:] in esperado
                 or "PartName" not in dict(t[1])}
    if esperados != tipos(pb):
        problemas.append(f"[Content_Types].xml: {esperados ^ tipos(pb)}")
    ta = titulos_app(pa)
    if ta is not None and [t for t in ta if t not in quitadas] != titulos_app(pb):
        problemas.append("docProps/app.xml: los títulos de hojas no coinciden")
    return problemas



def textos(z):
    if TEXTOS not in z.namelist():
        return []
    return re.findall(rb"<si(?:\s*/>|>.*?</si>)", z.read(TEXTOS), re.S)


def revisar_zip(ruta):
    """Recorre los encabezados locales; devuelve (problemas, orden físico)."""
    datos = open(ruta, "rb").read()
    problemas = []
    with zipfile.ZipFile(ruta) as z:
        infos = sorted(z.infolist(), key=lambda i: i.header_offset)
        fin_anterior = 0
        for info in infos:
            p = info.header_offset
            if p != fin_anterior:
                problemas.append(f"{info.filename}: hueco o traslape antes de la entrada")
            (firma, _, _, metodo, _, _, crc, comp, tam, n, extra) = struct.unpack(
                "<IHHHHHIIIHH", datos[p:p + 30])
            nombre = datos[p + 30:p + 30 + n].decode("utf-8")
            if (firma, nombre, metodo, crc, comp, tam) != (
                    0x04034B50, info.filename, info.compress_type, info.CRC,
                    info.compress_size, info.file_size):
                problemas.append(f"{info.filename}: encabezado local distinto del central")
            inicio = p + 30 + n + extra
            flujo = datos[inicio:inicio + info.compress_size]
            crudo = zlib.decompress(flujo, -15) if metodo == 8 else flujo
            if len(crudo) != tam or zlib.crc32(crudo) & 0xFFFFFFFF != crc:
                problemas.append(f"{info.filename}: CRC o tamaño incorrecto")
            fin_anterior = inicio + info.compress_size
    return problemas, [i.filename for i in infos]


def celdas(xml, sst):
    """Devuelve filas, {(fila, col): contenido}, orden y avisos de compatibilidad."""
    raiz = etree.fromstring(xml, etree.XMLParser(huge_tree=True))
    datos = raiz.find(f"{NS}sheetData")
    filas, mapa, orden = [], {}, []
    avisos = {"compartida sin r": 0, "sin r tras salto de fila": 0}
    fila_prev = 0
    for fila in datos:
        if not isinstance(fila.tag, str):  # comentario o instrucción: se compara tal cual
            orden.append((fila_prev, etree.tostring(fila)))
            continue
        if fila.tag != f"{NS}row":
            raise ValueError(f"elemento inesperado en sheetData: {fila.tag}")
        r = int(fila.get("r")) if fila.get("r") else fila_prev + 1
        contigua = r == fila_prev + 1
        fila_prev = r
        filas.append((r, dict(fila.attrib), fila.text, fila.tail))
        col_prev = 0
        for c in fila:
            if not isinstance(c.tag, str):
                orden.append((r, etree.tostring(c)))
                continue
            if c.tag != f"{NS}c":
                raise ValueError(f"fila {r}: elemento inesperado {c.tag}")
            ref = c.get("r")
            if ref:
                m = re.fullmatch(r"([A-Z]+)(\d+)", ref)
                if int(m.group(2)) != r:
                    raise ValueError(f"{ref} fuera de la fila {r}")
                col = columna(m.group(1))
            else:
                col = col_prev + 1
                f = c.find(f"{NS}f")
                if f is not None and f.get("t") == "shared":
                    avisos["compartida sin r"] += 1
                if not contigua:
                    avisos["sin r tras salto de fila"] += 1
            if col <= col_prev:
                raise ValueError(f"fila {r}: columna {col} fuera de orden")
            col_prev = col
            attrs = {k: v for k, v in c.attrib.items() if k != "r"}
            hijos = []
            for h in c:
                if attrs.get("t") == "s" and h.tag == f"{NS}v":
                    hijos.append(b"<v>" + sst[int(h.text)] + b"</v>")
                else:
                    hijos.append(etree.tostring(h, method="c14n"))
            mapa[(r, col)] = (attrs, b"".join(hijos), c.text, c.tail)
            orden.append((r, col))
    return filas, mapa, orden, avisos


def fuera_de_datos(xml):
    i = xml.find(b"<sheetData")
    j = xml.find(b"</sheetData>")
    if j < 0:  # <sheetData/>
        return xml[:i], xml[xml.find(b">", i) + 1:]
    return xml[:i], xml[j:]


def mismos_pixeles(a, b):
    from PIL import Image

    ia, ib = Image.open(io.BytesIO(a)), Image.open(io.BytesIO(b))
    return ia.size == ib.size and ia.convert("RGBA").tobytes() == ib.convert("RGBA").tobytes()


def diferencias(nombre, a, b):
    partir = lambda x: x.decode("utf-8").replace("><", ">\n<").splitlines()
    for linea in difflib.unified_diff(partir(a), partir(b), lineterm="", n=0):
        if not linea.startswith(("---", "+++", "@@")):
            print(f"    {nombre}: {linea}")


def main(original, reducido, quitadas):
    errores = 0
    problemas, fisico_b = revisar_zip(reducido)
    for p in problemas:
        print(f"zip: {p}")
        errores += 1
    _, fisico_a = revisar_zip(original)
    if [n for n in fisico_a if n in fisico_b] != fisico_b:
        print("zip: las partes no están en el orden físico del original")
        errores += 1
    with zipfile.ZipFile(original) as za, zipfile.ZipFile(reducido) as zb:
        pa = {n: za.read(n) for n in za.namelist()}
        pb = {n: zb.read(n) for n in zb.namelist()}
        for p in estructura(pb):
            print(f"paquete: {p}")
            errores += 1
        if quitadas:
            for p in revisar_quitadas(pa, pb, quitadas):
                print(f"hoja quitada: {p}")
                errores += 1
        hojas_a, hojas_b = hojas(pa), hojas(pb)
        esperadas = [h for h in hojas_a if h not in quitadas]
        if list(hojas_b) != esperadas:
            print(f"Hojas distintas: {list(hojas_b)} vs {esperadas}")
            return 1
        sst_a, sst_b = textos(za), textos(zb)
        partes_hoja = set(hojas_a.values())
        nombres_a = [i.filename for i in za.infolist()]
        nombres_b = [i.filename for i in zb.infolist()]
        sobrantes = [n for n in nombres_b if n not in nombres_a]
        faltantes = [n for n in nombres_a if n not in nombres_b]
        if sobrantes or [n for n in nombres_a if n in nombres_b] != nombres_b:
            print(f"Partes nuevas o reordenadas: {sobrantes}")
            errores += 1
        if faltantes and not quitadas:
            print(f"Faltan partes: {faltantes}")
            errores += 1
        for n in faltantes:
            print(f"  parte quitada: {n}")
        for n in nombres_b:
            if n in partes_hoja:
                continue
            a, b = za.read(n), zb.read(n)
            if a == b:
                continue
            if n.lower().endswith(".png"):
                if mismos_pixeles(a, b):
                    print(f"  {n}: {len(a):,} -> {len(b):,} bytes, mismos píxeles")
                else:
                    print(f"{n}: la imagen cambió")
                    errores += 1
                continue
            if quitadas and n in AJUSTADAS:
                if n != TEXTOS:
                    print(f"  cambios en {n}:")
                    diferencias(n, a, b)
                continue
            print(f"{n}: distinto")
            errores += 1
        if quitadas:
            # Cada texto que queda debe existir, en el mismo orden, en el original.
            it = iter(sst_a)
            if not all(any(t == x for x in it) for t in sst_b):
                print("sharedStrings: hay textos nuevos o reordenados")
                errores += 1
            print(f"  sharedStrings: {len(sst_a):,} -> {len(sst_b):,} textos")
        for nombre, parte_b in hojas_b.items():
            parte_a = hojas_a[nombre]
            a, b = za.read(parte_a), zb.read(parte_b)
            antes = errores
            if b"<sheetData" not in a:
                if a != b:
                    print(f"{nombre}: distinta")
                    errores += 1
                continue
            if fuera_de_datos(a) != fuera_de_datos(b):
                print(f"{nombre}: cambió algo fuera de sheetData")
                errores += 1
            filas_a, celdas_a, orden_a, avisos_a = celdas(a, sst_a)
            filas_b, celdas_b, orden_b, avisos = celdas(b, sst_b)
            if filas_a != filas_b:
                print(f"{nombre}: filas distintas")
                errores += 1
            if orden_a != orden_b or celdas_a != celdas_b:
                dif = {k for k in celdas_a.keys() | celdas_b.keys()
                       if celdas_a.get(k) != celdas_b.get(k)}
                print(f"{nombre}: {len(dif):,} celdas distintas, p. ej. {sorted(dif)[:5]}")
                errores += 1
            for aviso, n in avisos.items():
                if n > avisos_a[aviso]:  # sólo cuenta lo que introdujo la reducción
                    print(f"{nombre}: {n - avisos_a[aviso]:,} celdas {aviso} "
                          "(algunos lectores las acomodan mal)")
                    errores += 1
            if errores == antes:
                con_valor = sum(1 for v in celdas_a.values() if v[1])
                print(f"{nombre}: {len(filas_a):,} filas, {len(celdas_a):,} celdas "
                      f"({con_valor:,} con contenido) idénticas")
    print("OK: contenido idéntico" if not errores else f"{errores} diferencias")
    return 1 if errores else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("original")
    ap.add_argument("reducido")
    ap.add_argument("--quitada", action="append", default=[], metavar="NOMBRE")
    a = ap.parse_args()
    sys.exit(main(a.original, a.reducido, a.quitada))
