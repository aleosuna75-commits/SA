"""Inserta hojas nuevas en el .xlsb conservando intactos (bytes comprimidos incluidos) todos los demas
componentes, calcChain incluido. Solo se reemplazan workbook.bin, sus rels, [Content_Types].xml,
sharedStrings.bin y styles.bin, y se anexan las hojas nuevas."""
import zipfile, struct, re, os, shutil, subprocess, tempfile
from biff import records
from xlsbw import rec, wstr

CT_WS = 'application/vnd.ms-excel.worksheet'
REL_WS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet'

def leer_sst(src):
    z = zipfile.ZipFile(src); return sum(1 for rid, _ in records(z.read('xl/sharedStrings.bin')) if rid == 19)

def insertar(src, dst, hojas, xti_extra=(), cadenas=None, styles_bin=None):
    z = zipfile.ZipFile(src)
    wb = z.read('xl/workbook.bin')
    rels = z.read('xl/_rels/workbook.bin.rels').decode('utf-8')
    cts  = z.read('[Content_Types].xml').decode('utf-8')
    usados = {int(m) for m in re.findall(r'sheet(\d+)\.bin', ' '.join(z.namelist()))}
    next_sheet = max(usados) + 1
    next_rid = max(int(m) for m in re.findall(r'Id="rId(\d+)"', rels)) + 1
    max_tab = max(struct.unpack_from('<I', pl, 4)[0] for rid, pl in records(wb) if rid == 156)
    nuevos = [dict(nombre=nom, parte=f'xl/worksheets/sheet{next_sheet+i}.bin', rid=f'rId{next_rid+i}', tab=max_tab+1+i)
              for i, (nom, _) in enumerate(hojas)]
    out = bytearray()
    for rid, pl in records(wb):
        if rid == 144:
            for n in nuevos:
                out += rec(156, struct.pack('<II', 0, n['tab']) + wstr(n['rid']) + wstr(n['nombre']))
        if rid == 362 and xti_extra:
            (cn,) = struct.unpack_from('<I', pl, 0); cuerpo = pl[4:4+12*cn]
            for sb, a, b in xti_extra: cuerpo += struct.pack('<Iii', sb, a, b)
            pl = struct.pack('<I', cn + len(xti_extra)) + cuerpo
        out += rec(rid, pl)
    for n in nuevos:
        rels = rels.replace('</Relationships>', f'<Relationship Id="{n["rid"]}" Type="{REL_WS}" Target="{n["parte"].replace("xl/","")}"/></Relationships>')
        cts  = cts.replace('</Types>', f'<Override PartName="/{n["parte"]}" ContentType="{CT_WS}"/></Types>')
    partes = {'xl/workbook.bin': bytes(out), 'xl/_rels/workbook.bin.rels': rels.encode('utf-8'),
              '[Content_Types].xml': cts.encode('utf-8')}
    if cadenas is not None and cadenas.nuevas:
        o = bytearray()
        for rid, pl in records(z.read('xl/sharedStrings.bin')):
            if rid == 159:
                tot, uni = struct.unpack_from('<II', pl, 0)
                pl = struct.pack('<II', tot + len(cadenas.nuevas), uni + len(cadenas.nuevas))
            if rid == 160:
                for s in cadenas.nuevas: o += rec(19, b'\x00' + wstr(s))
            o += rec(rid, pl)
        partes['xl/sharedStrings.bin'] = bytes(o)
    if styles_bin is not None: partes['xl/styles.bin'] = styles_bin
    for n, (nom, b) in zip(nuevos, hojas): partes[n['parte']] = b
    z.close()
    # --- escribir: copia del original + zip -u de las partes modificadas/nuevas ---
    shutil.copyfile(src, dst)
    with tempfile.TemporaryDirectory() as td:
        for nombre, data in partes.items():
            p = os.path.join(td, nombre); os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'wb').write(data)
        r = subprocess.run(['zip', '-X', '-D', '-q', os.path.abspath(dst)] + list(partes.keys()), cwd=td,
                           capture_output=True, text=True)
        if r.returncode != 0: raise RuntimeError(r.stderr)
    return nuevos
