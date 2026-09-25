"""
Comprueba que dos .xlsx tienen exactamente el mismo contenido.

- Toda parte del paquete que no es hoja debe ser idéntica byte por byte.
- En cada hoja, lo que está fuera de <sheetData> debe ser idéntico, y dentro
  cada fila y cada celda debe coincidir en posición, atributos (salvo r),
  fórmula y valor. La posición de las celdas sin r se calcula como indica
  el estándar: columna de la celda anterior + 1.

Uso:
    python3 herramientas/verificar_xlsx.py ORIGINAL.xlsx REDUCIDO.xlsx
"""

import re
import sys
import zipfile

from lxml import etree

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
HOJA = re.compile(r"^xl/worksheets/[^/]+\.xml$")


def columna(letras):
    n = 0
    for ch in letras:
        n = n * 26 + (ord(ch) - 64)
    return n


def celdas(xml):
    """Devuelve {(fila, col): (atributos, hijos)} y los atributos de filas."""
    raiz = etree.fromstring(xml, etree.XMLParser(huge_tree=True))
    datos = raiz.find(f"{NS}sheetData")
    filas, mapa = [], {}
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
            col_prev = col
            attrs = {k: v for k, v in c.attrib.items() if k != "r"}
            hijos = b"".join(etree.tostring(h, method="c14n") for h in c)
            if (r, col) in mapa:
                raise ValueError(f"celda repetida en fila {r}, columna {col}")
            mapa[(r, col)] = (attrs, hijos)
    return filas, mapa


def fuera_de_datos(xml):
    return xml[: xml.find(b"<sheetData")], xml[xml.find(b"</sheetData>") :]


def main(original, reducido):
    errores = 0
    with zipfile.ZipFile(original) as za, zipfile.ZipFile(reducido) as zb:
        nombres_a = [i.filename for i in za.infolist()]
        nombres_b = [i.filename for i in zb.infolist()]
        if nombres_a != nombres_b:
            print("Las partes del paquete no coinciden")
            return 1
        for nombre in nombres_a:
            a, b = za.read(nombre), zb.read(nombre)
            if not HOJA.match(nombre):
                if a != b:
                    print(f"{nombre}: distinto")
                    errores += 1
                continue
            antes = errores
            if fuera_de_datos(a) != fuera_de_datos(b):
                print(f"{nombre}: cambió algo fuera de sheetData")
                errores += 1
            filas_a, celdas_a = celdas(a)
            filas_b, celdas_b = celdas(b)
            if filas_a != filas_b:
                print(f"{nombre}: filas distintas")
                errores += 1
            if celdas_a != celdas_b:
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
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
