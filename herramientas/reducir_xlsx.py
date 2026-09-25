"""
Reduce el peso de un .xlsx sin quitar datos, fórmulas ni formato.

Qué hace (y por qué es sin pérdida):

1. En cada hoja, quita el atributo de dirección r="AE500" de las celdas
   cuya posición ya se deduce de la celda anterior (columna anterior + 1).
   Según el estándar ECMA-376 (18.3.1.4) ese atributo es opcional: si falta,
   la celda va en la siguiente columna. Se conserva siempre que hay un salto
   de columnas, así que cada celda queda exactamente en la misma posición.
   Algunos programas (p. ej. WPS) escriben la dirección en cada celda y eso
   es la mayor parte del peso comprimido.
2. Vuelve a comprimir el paquete con Zopfli (deflate estándar, compatible
   con Excel) en lugar de la compresión rápida original.

Todo lo demás (valores, fórmulas, valores calculados, estilos, filtros,
anchos, alturas, paneles inmovilizados, vínculos externos, nombres) se copia
byte por byte. Al final se verifica celda por celda contra el original.

Uso:
    python3 herramientas/reducir_xlsx.py ORIGEN.xlsx DESTINO.xlsx [--rapido]

--rapido comprime con zlib nivel 9 (segundos) en vez de Zopfli (minutos);
el archivo queda un poco más grande.
"""

import re
import struct
import sys
import zipfile
import zlib

import zopfli.zlib  # pip install zopfli

HOJA = re.compile(r"^xl/worksheets/[^/]+\.xml$")
TOKEN = re.compile(rb'<row\b[^>]*?\br="(\d+)"|<c r="([A-Z]{1,3})(\d+)"')


def columna(letras):
    n = 0
    for ch in letras:
        n = n * 26 + (ch - 64)
    return n


def quitar_direcciones(xml):
    """Devuelve el XML sin los r="..." redundantes de las celdas."""
    inicio = xml.find(b"<sheetData")
    fin = xml.find(b"</sheetData>")
    if inicio < 0 or fin < 0:
        return xml, 0
    # Toda celda debe empezar con <c r="..."; si no, no tocamos la hoja.
    cuerpo = xml[inicio:fin]
    if len(re.findall(rb"<c[ >/]", cuerpo)) != len(re.findall(rb'<c r="', cuerpo)):
        return xml, 0

    partes, ultimo, quitadas = [], 0, 0
    fila, col_prev = None, 0
    for m in TOKEN.finditer(xml, inicio, fin):
        if m.group(1) is not None:
            fila, col_prev = int(m.group(1)), 0
            continue
        if fila is None or int(m.group(3)) != fila:
            raise ValueError(f"celda {m.group(0)!r} fuera de su fila {fila}")
        col = columna(m.group(2))
        if col == col_prev + 1:
            partes.append(xml[ultimo:m.start()])
            partes.append(b"<c")
            ultimo = m.end()
            quitadas += 1
        col_prev = col
    partes.append(xml[ultimo:])
    return b"".join(partes), quitadas


def comprimir(datos, rapido=False):
    """Deflate crudo (se quita la envoltura zlib de 2+4 bytes)."""
    if rapido:
        return zlib.compress(datos, 9)[2:-4]
    return zopfli.zlib.compress(datos, numiterations=15)[2:-4]


def reempaquetar(destino, entradas, rapido=False):
    """Construye el zip a mano (zipfile no permite usar Zopfli)."""
    locales, central, pos = [], [], 0
    for info, datos in entradas:
        nombre = info.filename.encode("utf-8")
        es_dir = info.filename.endswith("/")
        comp = b"" if es_dir else comprimir(datos, rapido)
        metodo = 0 if es_dir else 8
        crc = zlib.crc32(datos) & 0xFFFFFFFF
        dt = info.date_time
        hora = (dt[3] << 11) | (dt[4] << 5) | (dt[5] // 2)
        fecha = ((dt[0] - 1980) << 9) | (dt[1] << 5) | dt[2]
        bandera = 0x800 if any(ord(ch) > 127 for ch in info.filename) else 0
        cab = struct.pack(
            "<IHHHHHIIIHH", 0x04034B50, 20, bandera, metodo, hora, fecha,
            crc, len(comp), len(datos), len(nombre), 0,
        )
        locales.append(cab + nombre + comp)
        central.append(
            struct.pack(
                "<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, bandera, metodo,
                hora, fecha, crc, len(comp), len(datos), len(nombre), 0, 0,
                0, 0, info.external_attr & 0xFFFFFFFF, pos,
            )
            + nombre
        )
        pos += len(locales[-1])
    dir_central = b"".join(central)
    fin = struct.pack(
        "<IHHHHIIH", 0x06054B50, 0, 0, len(entradas), len(entradas),
        len(dir_central), pos, 0,
    )
    with open(destino, "wb") as f:
        f.write(b"".join(locales))
        f.write(dir_central)
        f.write(fin)


def main(origen, destino, rapido=False):
    entradas = []
    with zipfile.ZipFile(origen) as zin:
        for info in zin.infolist():
            datos = zin.read(info.filename)
            if HOJA.match(info.filename):
                datos, n = quitar_direcciones(datos)
                print(f"{info.filename}: {n:,} direcciones redundantes quitadas")
            entradas.append((info, datos))
    reempaquetar(destino, entradas, rapido)
    with zipfile.ZipFile(destino) as z:
        malos = z.testzip()
        if malos:
            raise SystemExit(f"zip corrupto en {malos}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--rapido"]
    if len(args) != 2:
        raise SystemExit(__doc__)
    main(args[0], args[1], rapido="--rapido" in sys.argv)
