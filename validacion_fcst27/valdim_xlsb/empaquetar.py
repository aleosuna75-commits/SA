"""Inserta hojas nuevas en el .xlsb original sin tocar nada mas."""
import zipfile, struct, re, shutil
from biff import records, rd_xlwstr
from xlsbw import rec, wstr

CT_WS = 'application/vnd.ms-excel.worksheet'
REL_WS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet'

def leer_sst(src):
    z = zipfile.ZipFile(src); n = 0
    for rid, pl in records(z.read('xl/sharedStrings.bin')):
        if rid == 19: n += 1
    return n

def insertar(src, dst, hojas, xti_extra=(), cadenas=None):
    """hojas: lista de (nombre, bytes de la hoja). xti_extra: lista de (supbook, tab1, tab2)."""
    z = zipfile.ZipFile(src)
    wb = z.read('xl/workbook.bin')
    rels = z.read('xl/_rels/workbook.bin.rels').decode('utf-8')
    cts  = z.read('[Content_Types].xml').decode('utf-8')

    # --- numeros libres ---
    usados = {int(m) for m in re.findall(r'sheet(\d+)\.bin', ' '.join(z.namelist()))}
    next_sheet = max(usados) + 1
    next_rid = max(int(m) for m in re.findall(r'Id="rId(\d+)"', rels)) + 1
    max_tab = 0
    for rid, pl in records(wb):
        if rid == 156:
            max_tab = max(max_tab, struct.unpack_from('<I', pl, 4)[0])
    next_tab = max_tab + 1

    nuevos = []
    for i, (nom, _b) in enumerate(hojas):
        nuevos.append(dict(nombre=nom, parte=f'xl/worksheets/sheet{next_sheet+i}.bin',
                           rid=f'rId{next_rid+i}', tab=next_tab + i))

    # --- workbook.bin ---
    out = bytearray()
    for rid, pl in records(wb):
        if rid == 144:                      # BrtEndBundleShs -> insertar antes
            for n in nuevos:
                out += rec(156, struct.pack('<II', 0, n['tab']) + wstr(n['rid']) + wstr(n['nombre']))
        if rid == 362 and xti_extra:        # BrtExternSheet -> ampliar tabla Xti
            (cn,) = struct.unpack_from('<I', pl, 0)
            cuerpo = pl[4:4 + 12*cn]
            for sb, a, b in xti_extra:
                cuerpo += struct.pack('<Iii', sb, a, b)
            pl = struct.pack('<I', cn + len(xti_extra)) + cuerpo
        out += rec(rid, pl)
    wb_new = bytes(out)

    # --- rels: agregar hojas, quitar calcChain ---
    for n in nuevos:
        rels = rels.replace('</Relationships>',
            f'<Relationship Id="{n["rid"]}" Type="{REL_WS}" '
            f'Target="{n["parte"].replace("xl/","")}"/></Relationships>')
    rels = re.sub(r'<Relationship[^>]*calcChain[^>]*/>', '', rels)

    # --- content types: agregar hojas, quitar calcChain ---
    for n in nuevos:
        cts = cts.replace('</Types>',
            f'<Override PartName="/{n["parte"]}" ContentType="{CT_WS}"/></Types>')
    cts = re.sub(r'<Override[^>]*calcChain[^>]*/>', '', cts)

    # --- rescribir el zip ---
    # --- sharedStrings.bin: anexar cadenas nuevas ---
    sst_new = None
    if cadenas is not None and cadenas.nuevas:
        buf = z.read('xl/sharedStrings.bin')
        o = bytearray()
        for rid, pl in records(buf):
            if rid == 159:                 # BrtBeginSst
                tot, uni = struct.unpack_from('<II', pl, 0)
                pl = struct.pack('<II', tot + len(cadenas.nuevas), uni + len(cadenas.nuevas))
            if rid == 160:                 # BrtEndSst -> insertar antes
                for s in cadenas.nuevas:
                    o += rec(19, b'\x00' + wstr(s))
            o += rec(rid, pl)
        sst_new = bytes(o)

    reemplazos = {'xl/workbook.bin': wb_new,
                  'xl/_rels/workbook.bin.rels': rels.encode('utf-8'),
                  '[Content_Types].xml': cts.encode('utf-8')}
    if sst_new is not None:
        reemplazos['xl/sharedStrings.bin'] = sst_new
    omitir = {'xl/calcChain.bin'}
    zo = zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED, allowZip64=True)
    for it in z.infolist():
        if it.filename in omitir:
            continue
        data = reemplazos.get(it.filename) or z.read(it.filename)
        zo.writestr(it.filename, data, zipfile.ZIP_DEFLATED)
    for n, (nom, b) in zip(nuevos, hojas):
        zo.writestr(n['parte'], b, zipfile.ZIP_DEFLATED)
    zo.close(); z.close()
    return nuevos
