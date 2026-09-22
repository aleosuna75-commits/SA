import zipfile, struct
from biff import records, rd_xlwstr, colrow
import fmla

def sst(path):
    z = zipfile.ZipFile(path); out = []
    try: buf = z.read('xl/sharedStrings.bin')
    except KeyError: return out
    for rid, pl in records(buf):
        if rid == 19:
            s, _ = rd_xlwstr(pl, 1); out.append(s)
    return out

def _rk(u):
    fx100 = u & 1; fint = u & 2
    if fint:
        v = u >> 2
        if v & 0x20000000: v -= 0x40000000
        v = float(v)
    else:
        v = struct.unpack('<d', struct.pack('<Q', (u & 0xFFFFFFFC) << 32))[0]
    return v/100.0 if fx100 else v

def shared(path, part):
    """Collect shared(427)/array(426) formulas keyed by master cell."""
    z = zipfile.ZipFile(path); out = {}
    for rid, pl in records(z.read(part)):
        if rid in (426, 427):
            r1, r2, c1, c2 = struct.unpack_from('<IIII', pl, 0)
            o = 16
            o += 0 if rid == 427 else 1
            (cce,) = struct.unpack_from('<I', pl, o); o += 4
            out[(r1, c1)] = (pl[o:o+cce], rid)
    return out

def cells(path, part, ctx, strings, shr=None):
    if shr is None: shr = shared(path, part)
    z = zipfile.ZipFile(path); row = 0
    for rid, pl in records(z.read(part)):
        if rid == 0:
            (row,) = struct.unpack_from('<I', pl, 0); continue
        if rid not in (1,2,4,5,6,7,8,9,10,11): continue
        (col,) = struct.unpack_from('<I', pl, 0)
        o = 8; val = None; f = None
        if rid == 1:
            yield row, col, None, None; continue
        if rid == 2:
            (u,) = struct.unpack_from('<I', pl, o); val = _rk(u); o += 4
        elif rid == 5:
            (val,) = struct.unpack_from('<d', pl, o); o += 8
        elif rid == 6:
            val, o = rd_xlwstr(pl, o)
        elif rid == 7:
            (i,) = struct.unpack_from('<I', pl, o); o += 4
            val = strings[i] if i < len(strings) else f'#S{i}'
        elif rid == 4:
            val = bool(pl[o]); o += 1
        elif rid in (8,9,10,11):
            if rid == 9:   (val,) = struct.unpack_from('<d', pl, o); o += 8
            elif rid == 8: val, o = rd_xlwstr(pl, o)
            elif rid == 10: val = bool(pl[o]); o += 1
            else: val = f'#ERR{pl[o]}'; o += 1
            o += 2
            (cce,) = struct.unpack_from('<I', pl, o); o += 4
            rgce = pl[o:o+cce]
            (cb,) = struct.unpack_from('<I', pl, o+cce)
            rgcb = pl[o+cce+4:o+cce+4+cb]
            if len(rgce) >= 5 and rgce[0] == 0x01:
                (mr,) = struct.unpack_from('<I', rgce, 1)
                mc = struct.unpack_from('<I', rgcb, 0)[0] if len(rgcb) >= 4 else col
                ent = shr.get((mr, mc))
                if ent: f = fmla.parse(ent[0], ctx, (row, col))
                else:   f = f'<shared@{colrow(mr,mc)}>'
            else:
                f = fmla.parse(rgce, ctx, (row, col))
        yield row, col, val, f
