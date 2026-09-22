"""Escritor minimo de hojas BIFF12 (.xlsb) para agregar hojas al libro original."""
import struct, zipfile, re, io

# ---------- framing ----------
def rec(rid, payload=b''):
    out = bytearray()
    if rid < 0x80:
        out.append(rid)
    else:
        out.append((rid & 0x7F) | 0x80); out.append((rid >> 7) & 0x7F)
    n = len(payload)
    while True:
        b = n & 0x7F; n >>= 7
        if n: out.append(b | 0x80)
        else:  out.append(b); break
    out += payload
    return bytes(out)

def wstr(s):
    b = s.encode('utf-16-le')
    return struct.pack('<I', len(s)) + b

# ---------- ptgs ----------
def _colf(col, crel=False, rrel=False):
    return (col & 0x3FFF) | (0x4000 if crel else 0) | (0x8000 if rrel else 0)

def area3d(ixti, r1, r2, c1, c2):
    "PtgArea3d clase referencia -> Hoja!$C$r1:$C$r2"
    return struct.pack('<BHIIHH', 0x3B, ixti, r1, r2, _colf(c1), _colf(c2))

def ref3d(ixti, r, c):
    "PtgRef3d clase valor -> Hoja!$C$r"
    return struct.pack('<BHIH', 0x5A, ixti, r, _colf(c))

def ref(r, c, crel=False, rrel=False):
    "PtgRef clase valor (misma hoja)"
    return struct.pack('<BIH', 0x44, r, _colf(c, crel, rrel))

def area(r1, r2, c1, c2):
    return struct.pack('<BIIHH', 0x45, r1, r2, _colf(c1), _colf(c2))

def num(v):
    if float(v).is_integer() and 0 <= v <= 65535:
        return struct.pack('<BH', 0x1E, int(v))
    return struct.pack('<Bd', 0x1F, float(v))

def txt(s):
    b = s.encode('utf-16-le')
    return struct.pack('<BH', 0x17, len(s)) + b

def funcvar(nargs, iftab):
    return struct.pack('<BBH', 0x42, nargs, iftab)

UMINUS = b'\x13'; SUB = b'\x04'; ADD = b'\x03'; MUL = b'\x05'; DIV = b'\x06'
IF_SUMIFS = 482; IF_SUM = 4

# ---------- celdas ----------
def _cellhdr(col, style):
    return struct.pack('<II', col, style & 0xFFFFFF)

def c_blank(col, style=0):
    return rec(1, _cellhdr(col, style))

def c_num(col, v, style=0):
    return rec(5, _cellhdr(col, style) + struct.pack('<d', float(v)))

def c_str(col, s, style=0):
    "cadena en linea (BrtCellSt)"
    return rec(6, _cellhdr(col, style) + wstr(s))

def c_isst(col, isst, style=0):
    "cadena de la tabla compartida (BrtCellIsst) -- lo que escribe Excel"
    return rec(7, _cellhdr(col, style) + struct.pack('<I', isst))

class Cadenas:
    "Acumula cadenas nuevas para anexarlas a sharedStrings.bin"
    def __init__(self, base):
        self.base = base; self.nuevas = []; self.idx = {}
    def add(self, s):
        s = str(s)
        if s not in self.idx:
            self.idx[s] = self.base + len(self.nuevas)
            self.nuevas.append(s)
        return self.idx[s]

def c_fmla_num(col, cached, rgce, style=0):
    body = _cellhdr(col, style) + struct.pack('<d', float(cached)) + struct.pack('<H', 0)
    body += struct.pack('<I', len(rgce)) + rgce + struct.pack('<I', 0)
    return rec(9, body)

def c_fmla_str(col, cached, rgce, style=0):
    body = _cellhdr(col, style) + wstr(cached) + struct.pack('<H', 0)
    body += struct.pack('<I', len(rgce)) + rgce + struct.pack('<I', 0)
    return rec(8, body)

def rowhdr(r):
    # rw, ixfe, miyRw, flags, flags2, ccolspan=0
    return rec(0, struct.pack('<IIHHBI', r, 0, 300, 0, 0, 0))

# ---------- hoja ----------
WSVIEW = bytes.fromhex('980300000000000000000000000040000000640000000000000000000000')
SEL    = struct.pack('<IIIII', 3, 0, 0, 0, 1) + struct.pack('<IIII', 0, 0, 0, 0)
FMTPR  = bytes.fromhex('6d0b00000a00f00000000000')

def _col_de(celda):
    """Extrae la columna de un registro de celda ya serializado."""
    p = 1 if celda[0] < 0x80 else 2
    while celda[p] & 0x80: p += 1
    p += 1
    return struct.unpack_from('<I', celda, p)[0]

def sheet_bin(rows, ncols):
    """rows: dict {fila0: [bytes de celdas]}. Ordena las celdas por columna."""
    orden = {}
    for r, cs in rows.items():
        pares = sorted(((_col_de(c), i, c) for i, c in enumerate(cs)), key=lambda x: (x[0], x[1]))
        cols = [p[0] for p in pares]
        if len(set(cols)) != len(cols):
            raise ValueError(f'fila {r+1}: columnas repetidas')
        orden[r] = [p[2] for p in pares]
    rows = orden
    out = bytearray()
    out += rec(129)
    rr = sorted(rows)
    r1, r2 = (rr[0], rr[-1]) if rr else (0, 0)
    out += rec(148, struct.pack('<IIII', r1, r2, 0, max(ncols - 1, 0)))
    out += rec(133); out += rec(137, WSVIEW); out += rec(152, SEL)
    out += rec(138); out += rec(134)
    out += rec(485, FMTPR)
    out += rec(145)
    for r in rr:
        out += rowhdr(r)
        for cb in rows[r]:
            out += cb
    out += rec(146)
    out += rec(130)
    return bytes(out)
