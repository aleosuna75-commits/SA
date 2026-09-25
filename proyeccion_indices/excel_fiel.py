# -*- coding: utf-8 -*-
"""
Utilidades para guardar libros con openpyxl conservando lo mas fielmente posible el archivo original.

openpyxl conserva valores, formatos, formulas, filtros, nombres definidos, anchos y paneles, pero:
  * escribe los numeros con 16 digitos significativos (no 17) -> se parchea para escribir repr(float),
    que reproduce exactamente el valor original;
  * no escribe el atributo outlineLevelCol (barra de agrupacion de columnas) -> se fija antes de guardar;
  * reinterpreta el pie de pagina de la etiqueta de sensibilidad ("&1#" invisible) -> despues de guardar
    se vuelve a poner el bloque <headerFooter> original de cada hoja.
Ademas, el guardado es atomico (archivo temporal + reemplazo) y avisa si el archivo esta abierto en Excel.
"""
from __future__ import annotations

import html
import math
import os
import posixpath
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import openpyxl.cell._writer as _writer_celdas

_SAFE_STRING_ORIGINAL = _writer_celdas.safe_string


def _safe_string_17(value):
    if isinstance(value, float) and math.isfinite(value):
        return repr(float(value))          # float() normaliza subclases (p.ej. np.float64)
    return _SAFE_STRING_ORIGINAL(value)


def parche_precision():
    """Escribe los flotantes con repr (ida y vuelta exacta) en lugar de '%.16g'."""
    _writer_celdas.safe_string = _safe_string_17


def fijar_esquema_columnas(wb):
    for ws in wb.worksheets:
        niveles = [d.outline_level for d in ws.column_dimensions.values() if d.outline_level]
        if niveles:
            ws.column_dimensions.max_outline = max(niveles)


def _hojas_xml(z: zipfile.ZipFile) -> dict:
    """{nombre de hoja: ruta del xml dentro del zip}."""
    wbxml = z.read("xl/workbook.xml").decode("utf-8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    destino = {}
    for rel in re.findall(r"<Relationship\b[^>]*>", rels):
        rid = re.search(r'\bId="([^"]+)"', rel)
        tgt = re.search(r'\bTarget="([^"]+)"', rel)
        if rid and tgt:
            t = html.unescape(tgt.group(1))
            destino[rid.group(1)] = posixpath.normpath(t.lstrip("/") if t.startswith("/") else posixpath.join("xl", t))
    hojas = {}
    for hoja in re.findall(r"<sheet\b[^>]*>", wbxml):
        nombre = re.search(r'\bname="([^"]+)"', hoja)
        rid = re.search(r'\br:id="([^"]+)"', hoja)
        if nombre and rid and rid.group(1) in destino:
            hojas[html.unescape(nombre.group(1))] = destino[rid.group(1)]
    return hojas


_PATRON_HF = re.compile(r"<headerFooter\b[^>]*/>|<headerFooter\b.*?</headerFooter>", re.S)


def restaurar_encabezados(original: Path, salida: Path) -> int:
    """Vuelve a poner en `salida` el bloque <headerFooter> de cada hoja de `original` (mismo nombre)."""
    if not Path(original).exists():
        return 0
    with zipfile.ZipFile(original) as zo:
        hojas_o = _hojas_xml(zo)
        bloques = {}
        for nombre, ruta in hojas_o.items():
            m = _PATRON_HF.search(zo.read(ruta).decode("utf-8"))
            if m:
                bloques[nombre] = m.group(0)
    if not bloques:
        return 0
    with zipfile.ZipFile(salida) as zs:
        hojas_s = _hojas_xml(zs)
        reemplazos = {}
        for nombre, bloque in bloques.items():
            ruta = hojas_s.get(nombre)
            if not ruta:
                continue
            xml = zs.read(ruta).decode("utf-8")
            if _PATRON_HF.search(xml):
                reemplazos[ruta] = _PATRON_HF.sub(lambda _m: bloque, xml, count=1)
            else:
                print(f"   Aviso: la hoja '{nombre}' perdio su encabezado/pie de pagina al guardar "
                      "(p.ej. etiqueta de sensibilidad); revisalo en Excel.")
        if not reemplazos:
            return 0
        fd, tmp = tempfile.mkstemp(suffix=".xlsx", dir=str(Path(salida).parent))
        os.close(fd)
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zt:
            for item in zs.infolist():
                datos = reemplazos[item.filename].encode("utf-8") if item.filename in reemplazos \
                    else zs.read(item.filename)
                zt.writestr(item, datos)
    os.replace(tmp, salida)
    return len(reemplazos)


def verificar_escritura(rutas) -> None:
    """Falla de inmediato (antes del calculo) si alguna salida esta abierta en Excel o en otro programa."""
    bloqueadas = []
    for ruta in rutas:
        ruta = Path(ruta)
        if ruta.exists():
            try:
                with open(ruta, "a"):
                    pass
            except PermissionError:
                bloqueadas.append(ruta.name)
    if bloqueadas:
        raise SystemExit("Cierra estos archivos (estan abiertos en Excel u otro programa) y vuelve a correr: "
                         + ", ".join(bloqueadas))


def guardar_libro(wb, ruta: Path, original: Path | None = None) -> None:
    """Guarda con los parches de fidelidad, de forma atomica y con mensaje claro si el archivo esta abierto."""
    ruta = Path(ruta)
    parche_precision()
    fijar_esquema_columnas(wb)
    fd, tmp = tempfile.mkstemp(suffix=".xlsx", dir=str(ruta.parent))
    os.close(fd)
    try:
        wb.save(tmp)
        if original is not None:
            try:
                restaurar_encabezados(original, Path(tmp))
            except Exception as e:  # noqa: BLE001
                print(f"   Aviso: no se pudo restaurar el encabezado/pie de pagina original de {ruta.name}: {e!r}")
        try:
            os.replace(tmp, ruta)
        except PermissionError as e:
            raise SystemExit(f"No se pudo escribir {ruta.name}: esta abierto en Excel u otro programa. "
                             "Cierralo y vuelve a correr.") from e
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def copiar(origen: Path, destino: Path) -> None:
    try:
        shutil.copyfile(origen, destino)
    except PermissionError as e:
        raise SystemExit(f"No se pudo escribir {Path(destino).name}: esta abierto en Excel u otro programa. "
                         "Cierralo y vuelve a correr.") from e
