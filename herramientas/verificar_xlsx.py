"""
Comprueba que dos .xlsx tienen exactamente el mismo contenido.

- Toda parte del paquete que no es hoja debe ser idéntica byte por byte,
  salvo las imágenes PNG, que deben tener exactamente los mismos píxeles.
- En cada hoja, lo que está fuera de <sheetData> debe ser idéntico, y dentro
  cada fila y cada celda debe coincidir en posición, atributos (salvo r),
  fórmula y valor. La posición de las celdas sin r se calcula como indica
  el estándar: columna de la celda anterior + 1. Las celdas de texto
  compartido se comparan por el texto, no por su número de índice.

Con --quitada NOMBRE se acepta que esa hoja ya no esté: se exige que falten
sólo ella y sus partes propias, y se muestran los cambios en el índice del
libro, relaciones, tipos y propiedades para revisarlos.

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
import sys
import zipfile

from lxml import etree

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
TEXTOS = "xl/sharedStrings.xml"
AJUSTADAS = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels",
             "[Content_Types].xml", "docProps/app.xml", TEXTOS}


def columna(letras):
    n = 0
    for ch in letras:
        n = n * 26 + (ord(ch) - 64)
    return n


def hojas(z):
    """{nombre de hoja: parte} en el orden del libro."""
    rels = {}
    for e in re.findall(rb"<Relationship\b[^>]*/>", z.read("xl/_rels/workbook.xml.rels")):
        rid = re.search(rb'\sId="([^"]*)"', e).group(1)
        destino = re.search(rb'\sTarget="([^"]*)"', e).group(1).decode()
        rels[rid] = posixpath.normpath(posixpath.join("xl", destino))
    salida = {}
    for e in re.findall(rb"<sheet\b[^>]*/>", z.read("xl/workbook.xml")):
        nombre = html.unescape(re.search(rb'\sname="([^"]*)"', e).group(1).decode())
        salida[nombre] = rels[re.search(rb'\s\w+:id="([^"]*)"', e).group(1)]
    return salida


def textos(z):
    if TEXTOS not in z.namelist():
        return []
    return re.findall(rb"<si(?:\s*/>|>.*?</si>)", z.read(TEXTOS), re.S)


def celdas(xml, sst):
    """Devuelve {(fila, col): (atributos, hijos)} y los atributos de filas."""
    raiz = etree.fromstring(xml, etree.XMLParser(huge_tree=True))
    datos = raiz.find(f"{NS}sheetData")
    filas, mapa, orden = [], {}, []
    fila_prev = 0
    for fila in datos:
        r = int(fila.get("r")) if fila.get("r") else fila_prev + 1
        fila_prev = r
        filas.append((r, dict(fila.attrib)))
        col_prev = 0
        for c in fila:
            ref = c.get("r")
            if ref:
                m = re.fullmatch(r"([A-Z]+)(\d+)", ref)
                if int(m.group(2)) != r:
                    raise ValueError(f"{ref} fuera de la fila {r}")
                col = columna(m.group(1))
            else:
                col = col_prev + 1
            if col <= col_prev:
                raise ValueError(f"fila {r}: columna {col} fuera de orden")
            col_prev = col
            attrs = {k: v for k, v in c.attrib.items() if k != "r"}
            if attrs.get("t") == "s":
                hijos = sst[int(c.find(f"{NS}v").text)]
            else:
                hijos = b"".join(etree.tostring(h, method="c14n") for h in c)
            mapa[(r, col)] = (attrs, hijos)
            orden.append((r, col))
    return filas, mapa, orden


def mismos_pixeles(a, b):
    from PIL import Image

    ia, ib = Image.open(io.BytesIO(a)), Image.open(io.BytesIO(b))
    return ia.size == ib.size and ia.convert("RGBA").tobytes() == ib.convert("RGBA").tobytes()


def fuera_de_datos(xml):
    return xml[: xml.find(b"<sheetData")], xml[xml.find(b"</sheetData>") :]


def diferencias(nombre, a, b):
    partir = lambda x: x.decode("utf-8").replace("><", ">\n<").splitlines()
    for linea in difflib.unified_diff(partir(a), partir(b), lineterm="", n=0):
        if not linea.startswith(("---", "+++", "@@")):
            print(f"    {nombre}: {linea}")


def main(original, reducido, quitadas):
    errores = 0
    with zipfile.ZipFile(original) as za, zipfile.ZipFile(reducido) as zb:
        hojas_a, hojas_b = hojas(za), hojas(zb)
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
            if fuera_de_datos(a) != fuera_de_datos(b):
                print(f"{nombre}: cambió algo fuera de sheetData")
                errores += 1
            filas_a, celdas_a, orden_a = celdas(a, sst_a)
            filas_b, celdas_b, orden_b = celdas(b, sst_b)
            if filas_a != filas_b:
                print(f"{nombre}: filas distintas")
                errores += 1
            if orden_a != orden_b or celdas_a != celdas_b:
                dif = {k for k in celdas_a.keys() | celdas_b.keys()
                       if celdas_a.get(k) != celdas_b.get(k)}
                print(f"{nombre}: {len(dif):,} celdas distintas, p. ej. {sorted(dif)[:5]}")
                errores += 1
            if errores == antes:
                con_valor = sum(1 for _, h in celdas_a.values() if h)
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
