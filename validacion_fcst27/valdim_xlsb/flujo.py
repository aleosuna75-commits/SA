"""Lectura parcial y segura de registros BIFF12 de una parte grande del zip."""
import zipfile, struct
def recs(buf):
    p = 0; n = len(buf)
    while p < n:
        b = buf[p]; rid = b & 0x7F; q = p + 1
        if b & 0x80:
            if q >= n: return
            rid |= (buf[q] & 0x7F) << 7; q += 1
        sz = 0; sh = 0; ok = False
        for _ in range(4):
            if q >= n: return
            c = buf[q]; q += 1; sz |= (c & 0x7F) << sh; sh += 7
            if not (c & 0x80): ok = True; break
        if not ok or q + sz > n: return
        yield rid, buf[q:q+sz]; p = q + sz
def leer_inicio(F, parte, nbytes):
    z = zipfile.ZipFile(F)
    with z.open(parte) as fh: return fh.read(nbytes)
