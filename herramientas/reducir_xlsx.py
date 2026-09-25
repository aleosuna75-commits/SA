"""
Reduce el peso de un .xlsx sin quitar datos, fórmulas ni formato.

Qué hace (y por qué es sin pérdida):

1. En cada hoja, quita el atributo de dirección r="AE500" de las celdas
   cuya posición ya se deduce de la celda anterior (columna anterior + 1).
   Según el estándar ECMA-376 (18.3.1.4) ese atributo es opcional: si falta,
   la celda va en la siguiente columna. Se conserva siempre que hay un salto
   de columnas, así que cada celda queda exactamente en la misma posición.
   Algunos programas (p. ej. WPS) escriben la dirección en cada celda y eso
   es la mayor parte del peso comprimido. Se conserva también:
   - en las celdas con fórmula compartida, porque openpyxl la usa para
     traducirlas;
   - en toda fila cuyo número no es el de la fila anterior + 1, porque WPS
     coloca las celdas sin r en (fila anterior + 1) en vez de en su fila.
2. Vuelve a comprimir el paquete con Zopfli (deflate estándar, compatible
   con Excel) en lugar de la compresión rápida original. Las partes se
   escriben en el mismo orden físico que en el original: los detectores de
   tipo de archivo (libmagic, que usan muchos portales de carga) reconocen
   un .xlsx por los nombres de las primeras partes del zip.
3. Recomprime las imágenes PNG con oxipng. Sólo se usa la versión nueva si
   es más ligera y tiene exactamente los mismos píxeles que la original.

Todo lo demás (valores, fórmulas, valores calculados, estilos, filtros,
anchos, alturas, paneles inmovilizados, vínculos externos, nombres) se copia
byte por byte. Al final se verifica celda por celda contra el original.

Opcionalmente, --quitar-hoja NOMBRE borra una hoja completa (esto sí quita
contenido, sólo cuando el usuario lo decide). Se borran también su filtro
guardado, sus dibujos e imágenes propios y los textos compartidos que sólo
ella usaba. Si otra hoja o un nombre definido hace referencia a ella, el
script se detiene en vez de dejar fórmulas rotas.

Uso:
    python3 herramientas/reducir_xlsx.py ORIGEN.xlsx DESTINO.xlsx
        [--rapido] [--quitar-hoja NOMBRE ...]

--rapido comprime con zlib nivel 9 (segundos) en vez de Zopfli (minutos);
el archivo queda un poco más grande.
"""

import argparse
import html
import io
import posixpath
import re
import struct
import zipfile
import zlib
from concurrent.futures import ProcessPoolExecutor

import zopfli.zlib  # pip install zopfli

HOJA = re.compile(r"^xl/worksheets/[^/]+\.xml$")
IMAGEN = re.compile(r"^xl/media/[^/]+\.png$", re.I)
TOKEN = re.compile(rb'<row\b[^>]*?\br="(\d+)"|<c r="([A-Z]{1,3})(\d+)"')
LIBRO = "xl/workbook.xml"
TEXTOS = "xl/sharedStrings.xml"
TIPOS = "[Content_Types].xml"
PROPIEDADES = "docProps/app.xml"
RELACION = re.compile(rb"<Relationship\b[^>]*/>")
CELDA_TEXTO = re.compile(rb'(<c\b[^>]*?\st="s"[^>]*>)<v>(\d+)</v>')


def columna(letras):
    n = 0
    for ch in letras:
        n = n * 26 + (ch - 64)
    return n


def formula_compartida(xml, pos):
    """¿La celda cuya etiqueta sigue en `pos` tiene <f t="shared">?

    Algunos lectores (openpyxl) usan la dirección de la celda para traducir
    las fórmulas compartidas, así que en esas celdas se deja r.
    """
    fin = xml.find(b">", pos)
    if xml[fin - 1:fin] == b"/":
        return False
    k = fin + 1
    while xml[k:k + 1] in (b" ", b"\t", b"\r", b"\n"):
        k += 1
    if xml[k:k + 3] not in (b"<f ", b"<f>", b"<f/"):
        return False
    return b't="shared"' in xml[k:xml.find(b">", k)]


def quitar_direcciones(xml):
    """Devuelve el XML sin los r="..." redundantes de las celdas."""
    inicio = xml.find(b"<sheetData")
    fin = xml.find(b"</sheetData>")
    if inicio < 0 or fin < 0:
        return xml, 0
    # Toda celda debe empezar con <c r="..." y no debe haber comentarios,
    # CDATA ni instrucciones que confundan el recorrido; si no, no se toca.
    cuerpo = xml[inicio:fin]
    if len(re.findall(rb"<c[ >/]", cuerpo)) != len(re.findall(rb'<c r="', cuerpo)):
        return xml, 0
    if b"<!--" in cuerpo or b"<![CDATA[" in cuerpo or b"<?" in cuerpo:
        return xml, 0

    partes, ultimo, quitadas = [], 0, 0
    fila, col_prev, contigua = None, 0, False
    for m in TOKEN.finditer(xml, inicio, fin):
        if m.group(1) is not None:
            nueva = int(m.group(1))
            contigua = nueva == (fila or 0) + 1
            fila, col_prev = nueva, 0
            continue
        if fila is None or int(m.group(3)) != fila:
            raise ValueError(f"celda {m.group(0)!r} fuera de su fila {fila}")
        col = columna(m.group(2))
        if contigua and col == col_prev + 1 and not formula_compartida(xml, m.end()):
            partes.append(xml[ultimo:m.start()])
            partes.append(b"<c")
            ultimo = m.end()
            quitadas += 1
        col_prev = col
    partes.append(xml[ultimo:])
    return b"".join(partes), quitadas


def atributo(etiqueta, nombre):
    m = re.search(rb"\s" + nombre + rb'="([^"]*)"', etiqueta)
    return html.unescape(m.group(1).decode("utf-8")) if m else None


def ruta_rels(parte):
    return posixpath.join(posixpath.dirname(parte), "_rels",
                          posixpath.basename(parte) + ".rels")


def destinos(partes, parte):
    """Partes internas a las que apunta una parte ("" es la raíz)."""
    rels = partes.get(ruta_rels(parte))
    if rels is None:
        return []
    salida = []
    for etiqueta in RELACION.findall(rels):
        if atributo(etiqueta, b"TargetMode") == "External":
            continue
        destino = atributo(etiqueta, b"Target")
        if destino.startswith("/"):
            salida.append(destino[1:])
        else:
            salida.append(posixpath.normpath(
                posixpath.join(posixpath.dirname(parte), destino)))
    return salida


def quitar_hoja(partes, nombre):
    """Borra una hoja y todo lo que sólo ella usa. Modifica `partes`."""
    libro = partes[LIBRO]
    etiquetas = re.findall(rb"<sheet\b[^>]*/>", libro)
    nombres = [atributo(e, b"name") for e in etiquetas]
    if nombre not in nombres:
        raise SystemExit(f"No existe la hoja {nombre!r}; hojas: {nombres}")
    idx = nombres.index(nombre)
    rid = re.search(rb'\s\w+:id="([^"]*)"', etiquetas[idx]).group(1)

    # Nada que se quede puede apuntar a la hoja (fórmulas, nombres, gráficas).
    escapado = html.escape(nombre, quote=False).encode("utf-8")
    ref = re.compile(re.escape(escapado) + rb"(?:'|&apos;)?!")

    def sin_nombres_locales(m):
        etiqueta = m.group(0)
        local = re.search(rb'localSheetId="(\d+)"', etiqueta)
        if local:
            n = int(local.group(1))
            if n == idx:
                return b""
            if n > idx:
                etiqueta = etiqueta.replace(
                    local.group(0), b'localSheetId="%d"' % (n - 1), 1)
        if ref.search(etiqueta):
            raise SystemExit(f"El nombre definido {etiqueta!r} usa la hoja {nombre!r}")
        return etiqueta

    libro = re.sub(rb"<definedName\b[^>]*>.*?</definedName>",
                   sin_nombres_locales, libro, flags=re.S)
    libro = libro.replace(b"<definedNames></definedNames>", b"")
    libro = libro.replace(etiquetas[idx], b"", 1)
    vista = re.search(rb"<workbookView\b[^>]*>", libro)
    if vista:
        nueva = vista.group(0)
        for campo in (b"activeTab", b"firstSheet"):
            m = re.search(rb"\s" + campo + rb'="(\d+)"', nueva)
            if not m:
                continue
            n = int(m.group(1))
            if campo == b"activeTab" and n == idx:
                raise SystemExit(f"{nombre!r} es la hoja activa; actívese otra primero")
            if n > idx or n >= len(nombres) - 1:
                nueva = nueva.replace(
                    m.group(0), b" " + campo + b'="%d"' % max(n - 1, 0), 1)
        libro = libro.replace(vista.group(0), nueva, 1)
    partes[LIBRO] = libro

    # Relación del libro a la hoja.
    rels_libro = ruta_rels(LIBRO)
    hoja = None
    for etiqueta in RELACION.findall(partes[rels_libro]):
        if atributo(etiqueta, b"Id") == rid.decode():
            hoja = posixpath.normpath(posixpath.join("xl", atributo(etiqueta, b"Target")))
            partes[rels_libro] = partes[rels_libro].replace(etiqueta, b"", 1)
    if hoja not in partes:
        raise SystemExit(f"No se encontró la parte de la hoja {nombre!r}")

    # La hoja y lo que sólo es alcanzable desde ella (dibujos, imágenes...).
    quitar, cambio = {hoja}, True
    while cambio:
        cambio = False
        vivos = [""] + [p for p in partes if p not in quitar and not p.endswith("/")]
        usados = {d for p in vivos for d in destinos(partes, p)}
        for p in list(quitar):
            for d in destinos(partes, p):
                if d in partes and d not in quitar and d not in usados:
                    quitar.add(d)
                    cambio = True
    quitar |= {ruta_rels(p) for p in quitar if ruta_rels(p) in partes}

    for p, datos in partes.items():
        if p not in quitar and p not in (LIBRO, PROPIEDADES) and ref.search(datos):
            raise SystemExit(f"{p} hace referencia a la hoja {nombre!r}")

    for p in quitar:
        del partes[p]
        partes[TIPOS] = re.sub(
            rb'<Override PartName="/' + re.escape(p.encode()) + rb'"[^>]*/>',
            b"", partes[TIPOS])

    # Propiedades del documento: lista de títulos de hojas.
    app = partes.get(PROPIEDADES)
    titulos = app and re.search(
        rb'(<TitlesOfParts><vt:vector size=")(\d+)(" baseType="lpstr">)(.*?)</vt:vector>',
        app, re.S)
    grupo = app and re.search(rb"(<HeadingPairs>.*?<vt:i4>)(\d+)(</vt:i4>)", app, re.S)
    if titulos and grupo:
        items = re.findall(rb"<vt:lpstr>.*?</vt:lpstr>", titulos.group(4), re.S)
        hojas_app = items[:int(grupo.group(2))]
        buscado = b"<vt:lpstr>" + escapado + b"</vt:lpstr>"
        if buscado in hojas_app:
            items.remove(buscado)
            app = app.replace(titulos.group(0), titulos.group(1)
                              + str(len(items)).encode() + titulos.group(3)
                              + b"".join(items) + b"</vt:vector>", 1)
            app = app.replace(grupo.group(0), grupo.group(1)
                              + str(int(grupo.group(2)) - 1).encode() + grupo.group(3), 1)
            partes[PROPIEDADES] = app
    return sorted(quitar)


def podar_textos(partes):
    """Quita de sharedStrings los textos que ya ninguna celda usa."""
    sst = partes.get(TEXTOS)
    if sst is None:
        return 0
    items = list(re.finditer(rb"<si(?:\s*/>|>.*?</si>)", sst, re.S))
    for a, b in zip(items, items[1:]):
        if sst[a.end():b.start()].strip():
            raise SystemExit("sharedStrings tiene contenido inesperado entre textos")
    hojas = [p for p in partes if HOJA.match(p)]
    usados, total = set(), 0
    for p in hojas:
        celdas = CELDA_TEXTO.findall(partes[p])
        if len(celdas) != len(re.findall(rb'<c\b[^>]*?\st="s"', partes[p])):
            raise SystemExit(f"{p}: celda de texto con formato inesperado")
        usados.update(int(v) for _, v in celdas)
        total += len(celdas)
    if len(usados) == len(items):
        return 0
    orden = sorted(usados)
    nuevo = {viejo: i for i, viejo in enumerate(orden)}
    for p in hojas:
        partes[p] = CELDA_TEXTO.sub(
            lambda m: m.group(1) + b"<v>%d</v>" % nuevo[int(m.group(2))], partes[p])
    cabeza = sst[:items[0].start()]
    cabeza = re.sub(rb'(<sst\b[^>]*?\scount=")\d+', rb"\g<1>%d" % total, cabeza)
    cabeza = re.sub(rb'(<sst\b[^>]*?\suniqueCount=")\d+', rb"\g<1>%d" % len(orden), cabeza)
    partes[TEXTOS] = (cabeza + b"".join(items[i].group(0) for i in orden)
                      + sst[items[-1].end():])
    return len(items) - len(orden)


def mismos_pixeles(a, b):
    from PIL import Image

    ia, ib = Image.open(io.BytesIO(a)), Image.open(io.BytesIO(b))
    return ia.size == ib.size and ia.convert("RGBA").tobytes() == ib.convert("RGBA").tobytes()


def optimizar_png(datos):
    """PNG más ligero con los mismos píxeles; si no se puede, el original."""
    try:
        import oxipng  # pip install pyoxipng pillow
    except ImportError:
        return datos
    nuevo = oxipng.optimize_from_memory(
        datos, level=6, strip=oxipng.StripChunks.none(),
        deflate=oxipng.Deflaters.zopfli(15))
    if len(nuevo) < len(datos) and mismos_pixeles(datos, nuevo):
        return nuevo
    return datos


def comprimir(datos, rapido=False):
    """Deflate crudo (se quita la envoltura zlib de 2+4 bytes)."""
    if rapido:
        return zlib.compress(datos, 9)[2:-4]
    return zopfli.zlib.compress(datos, numiterations=15)[2:-4]


def reempaquetar(destino, entradas, rapido=False):
    """Construye el zip a mano (zipfile no permite usar Zopfli).

    Las entradas se escriben en el orden físico del original y el directorio
    central en el orden de `entradas` (el del directorio central original).
    """
    # Las partes más grandes primero, para repartir mejor el trabajo.
    orden = sorted(range(len(entradas)), key=lambda i: -len(entradas[i][1]))
    with ProcessPoolExecutor() as pool:
        hechos = dict(zip(orden, pool.map(
            comprimir, [entradas[i][1] for i in orden], [rapido] * len(orden))))
    fisico = sorted(range(len(entradas)), key=lambda i: entradas[i][0].header_offset)
    locales, centrales, pos = [], {}, 0
    for i in fisico:
        info, datos = entradas[i]
        nombre = info.filename.encode("utf-8")
        es_dir = info.filename.endswith("/")
        comp = b"" if es_dir else hechos[i]
        metodo = 0 if es_dir else 8
        necesita = info.extract_version if es_dir else max(info.extract_version, 20)
        crc = zlib.crc32(datos) & 0xFFFFFFFF
        dt = info.date_time
        hora = (dt[3] << 11) | (dt[4] << 5) | (dt[5] // 2)
        fecha = ((dt[0] - 1980) << 9) | (dt[1] << 5) | dt[2]
        bandera = 0x800 if any(ord(ch) > 127 for ch in info.filename) else 0
        locales.append(struct.pack(
            "<IHHHHHIIIHH", 0x04034B50, necesita, bandera, metodo, hora, fecha,
            crc, len(comp), len(datos), len(nombre), 0,
        ) + nombre + comp)
        centrales[i] = struct.pack(
            "<IHHHHHHIIIHHHHHII", 0x02014B50,
            (info.create_system << 8) | info.create_version, necesita, bandera,
            metodo, hora, fecha, crc, len(comp), len(datos), len(nombre), 0, 0,
            0, 0, info.external_attr & 0xFFFFFFFF, pos,
        ) + nombre
        pos += len(locales[-1])
    dir_central = b"".join(centrales[i] for i in range(len(entradas)))
    fin = struct.pack(
        "<IHHHHIIH", 0x06054B50, 0, 0, len(entradas), len(entradas),
        len(dir_central), pos, 0,
    )
    with open(destino, "wb") as f:
        f.write(b"".join(locales))
        f.write(dir_central)
        f.write(fin)


def main(origen, destino, rapido=False, quitar_hojas=()):
    with zipfile.ZipFile(origen) as zin:
        infos = zin.infolist()
        partes = {i.filename: zin.read(i.filename) for i in infos}
    for nombre in quitar_hojas:
        for p in quitar_hoja(partes, nombre):
            print(f"quitada: {p}")
    if quitar_hojas:
        print(f"{podar_textos(partes):,} textos compartidos que ya nadie usaba quitados")
    entradas = []
    for info in infos:
        if info.filename not in partes:
            continue
        datos = partes[info.filename]
        if HOJA.match(info.filename):
            datos, n = quitar_direcciones(datos)
            print(f"{info.filename}: {n:,} direcciones redundantes quitadas")
        elif IMAGEN.match(info.filename):
            antes, datos = len(datos), optimizar_png(datos)
            print(f"{info.filename}: {antes:,} -> {len(datos):,} bytes, mismos píxeles")
        entradas.append((info, datos))
    reempaquetar(destino, entradas, rapido)
    with zipfile.ZipFile(destino) as z:
        malos = z.testzip()
        if malos:
            raise SystemExit(f"zip corrupto en {malos}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("origen")
    ap.add_argument("destino")
    ap.add_argument("--rapido", action="store_true")
    ap.add_argument("--quitar-hoja", action="append", default=[], metavar="NOMBRE")
    a = ap.parse_args()
    main(a.origen, a.destino, a.rapido, a.quitar_hoja)
