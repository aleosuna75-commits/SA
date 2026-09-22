import zipfile, struct, io, re

def records(buf):
    """Yield (rectype, payload) from a BIFF12 stream."""
    p = 0; n = len(buf)
    while p < n:
        b = buf[p]; p += 1
        if b & 0x80:
            b2 = buf[p]; p += 1
            rid = (b & 0x7F) | ((b2 & 0x7F) << 7)
        else:
            rid = b
        sz = 0; shift = 0
        for _ in range(4):
            c = buf[p]; p += 1
            sz |= (c & 0x7F) << shift
            shift += 7
            if not (c & 0x80): break
        yield rid, buf[p:p+sz]
        p += sz

def rd_xlwstr(buf, off):
    (ln,) = struct.unpack_from('<I', buf, off)
    off += 4
    s = buf[off:off+2*ln].decode('utf-16-le', 'replace')
    return s, off + 2*ln

def colrow(r, c):
    s = ''
    c += 1
    while c:
        c, m = divmod(c-1, 26)
        s = chr(65+m) + s
    return f'{s}{r+1}'

def sheet_map(path):
    """Return list of (name, part) in workbook order."""
    z = zipfile.ZipFile(path)
    rels = {}
    for m in re.finditer(r'Id="([^"]+)"[^>]*Target="([^"]+)"',
                         z.read('xl/_rels/workbook.bin.rels').decode('utf-8','replace')):
        rels[m.group(1)] = m.group(2)
    out = []
    for rid, pl in records(z.read('xl/workbook.bin')):
        if rid == 156:  # BrtBundleSh
            (_hs, _iTab, _) = struct.unpack_from('<III', pl, 0)
            rel, off = rd_xlwstr(pl, 8)
            nm, off = rd_xlwstr(pl, off)
            t = rels.get(rel, '')
            if t.startswith('/xl/'): t = t[1:]
            elif not t.startswith('xl/'): t = 'xl/' + t
            out.append((nm, t))
    return out
