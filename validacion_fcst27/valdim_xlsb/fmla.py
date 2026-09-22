import zipfile, struct, re
from biff import records, rd_xlwstr, colrow

FTAB_NAMES = """0 COUNT|1 IF|2 ISNA|3 ISERROR|4 SUM|5 AVERAGE|6 MIN|7 MAX|8 ROW|9 COLUMN|
10 NA|11 NPV|12 STDEV|13 DOLLAR|14 FIXED|15 SIN|16 COS|17 TAN|18 ATAN|19 PI|20 SQRT|21 EXP|22 LN|
23 LOG10|24 ABS|25 INT|26 SIGN|27 ROUND|28 LOOKUP|29 INDEX|30 REPT|31 MID|32 LEN|33 VALUE|34 TRUE|
35 FALSE|36 AND|37 OR|38 NOT|39 MOD|40 DCOUNT|41 DSUM|42 DAVERAGE|43 DMIN|44 DMAX|45 DSTDEV|46 VAR|
47 DVAR|48 TEXT|49 LINEST|50 TREND|51 LOGEST|52 GROWTH|56 PV|57 FV|58 NPER|59 PMT|60 RATE|61 MIRR|
62 IRR|63 RAND|64 MATCH|65 DATE|66 TIME|67 DAY|68 MONTH|69 YEAR|70 WEEKDAY|71 HOUR|72 MINUTE|
73 SECOND|74 NOW|75 AREAS|76 ROWS|77 COLUMNS|78 OFFSET|82 SEARCH|83 TRANSPOSE|97 ATAN2|98 ASIN|
99 ACOS|100 CHOOSE|101 HLOOKUP|102 VLOOKUP|105 ISREF|109 LOG|111 CHAR|112 LOWER|113 UPPER|
114 PROPER|115 LEFT|116 RIGHT|117 EXACT|118 TRIM|119 REPLACE|120 SUBSTITUTE|121 CODE|124 FIND|
125 CELL|126 ISERR|127 ISTEXT|128 ISNUMBER|129 ISBLANK|130 T|131 N|140 DATEVALUE|141 TIMEVALUE|
142 SLN|143 SYD|144 DDB|148 INDIRECT|162 CLEAN|163 MDETERM|164 MINVERSE|165 MMULT|167 IPMT|
168 PPMT|169 COUNTA|183 PRODUCT|184 FACT|189 DPRODUCT|190 ISNONTEXT|193 STDEVP|194 VARP|
195 DSTDEVP|196 DVARP|197 TRUNC|198 ISLOGICAL|199 DCOUNTA|212 ROUNDUP|213 ROUNDDOWN|216 RANK|
219 ADDRESS|220 DAYS360|221 TODAY|222 VDB|227 MEDIAN|228 SUMPRODUCT|229 SINH|230 COSH|231 TANH|
232 ASINH|233 ACOSH|234 ATANH|235 DGET|244 INFO|247 DB|252 FREQUENCY|261 ERROR.TYPE|269 AVEDEV|
276 COMBIN|279 EVEN|285 FLOOR|288 CEILING|298 ODD|312 PEARSON|321 SUMSQ|325 LARGE|326 SMALL|
327 QUARTILE|328 PERCENTILE|329 PERCENTRANK|330 MODE|331 TRIMMEAN|336 CONCATENATE|337 POWER|
338 RADIANS|339 DEGREES|340 SUBTOTAL|345 SUMIF|346 COUNTIF|347 COUNTBLANK|350 ISPMT|351 DATEDIF|
348 ROMAN|350 GETPIVOTDATA|351 HYPERLINK|352 PHONETIC|353 AVERAGEA|354 MAXA|355 MINA|356 STDEVPA|
357 VARPA|358 STDEVA|359 VARA|371 RTD|
476 IFERROR|477 COUNTIFS|478 SUMIFS|479 AVERAGEIF|480 AVERAGEIFS|481 AGGREGATE|482 BINOM.DIST|
"""
FTAB = {}
for _e in FTAB_NAMES.replace("\n","").split("|"):
    _e = _e.strip()
    if not _e: continue
    _k, _v = _e.split(" ", 1)
    FTAB[int(_k)] = _v
# Verified empirically against this workbook (see NOTA in the report):
FTAB.update({482: "SUMIFS", 481: "COUNTIFS", 480: "IFERROR"})
ARITY = {1:3,2:1,3:1,4:-1,5:-1,6:-1,7:-1,8:1,9:1,10:0,15:1,16:1,17:1,18:1,19:0,20:1,21:1,22:1,
         23:1,24:1,25:1,26:1,27:2,29:-1,30:2,31:3,32:1,33:1,34:0,35:0,36:-1,37:-1,38:1,39:2,
         48:2,64:3,65:3,67:1,68:1,69:1,74:0,76:1,77:1,97:2,100:-1,101:-1,102:-1,105:1,111:1,
         112:1,113:1,114:1,115:-1,116:-1,117:2,118:1,119:4,120:-1,121:1,126:1,127:1,128:1,
         129:1,130:1,131:1,148:-1,169:-1,183:-1,190:1,197:-1,198:1,212:2,213:2,219:-1,221:0,
         227:-1,228:-1,285:2,288:2,336:-1,337:2,340:-1,341:-1,342:2,343:1,
         }

IFTABS_VISTOS = {}

def _fname(i):
    n = FTAB.get(i, f'FUNC{i}')
    IFTABS_VISTOS[i] = n
    return n

class Ctx:
    def __init__(self, path):
        z = zipfile.ZipFile(path)
        self.z = z
        from biff import sheet_map
        self.sheets = sheet_map(path)
        self.names = []
        self.xti = []
        self.supbooks = []
        for rid, pl in records(z.read('xl/workbook.bin')):
            if rid == 362:
                (cn,) = struct.unpack_from('<I', pl, 0)
                for i in range(cn):
                    self.xti.append(struct.unpack_from('<Iii', pl, 4+12*i))
            elif rid == 39:  # BrtName
                try:
                    flags, = struct.unpack_from('<I', pl, 0)
                    off = 9
                    nm, off = rd_xlwstr(pl, off)
                    self.names.append(nm)
                except Exception:
                    self.names.append('?')
            elif rid == 357:
                self.supbooks.append('SELF')
            elif rid == 355:
                self.supbooks.append('EXT')
    def sheetref(self, ixti):
        if ixti >= len(self.xti): return f'#XTI{ixti}'
        sb, a, b = self.xti[ixti]
        pre = '' if sb == 0 else f'[{sb}]'
        if a < 0: return pre.rstrip('!') or ''
        na = self.sheets[a][0] if a < len(self.sheets) else f'?{a}'
        nb = self.sheets[b][0] if b < len(self.sheets) else f'?{b}'
        s = na if a == b else f'{na}:{nb}'
        if re.search(r"[^A-Za-z0-9_.]", s): s = "'" + s.replace("'", "''") + "'"
        return pre + s + '!'

def _a1(col, rw, crel, rrel):
    s = ''
    c = col + 1
    while c:
        c, m = divmod(c-1, 26)
        s = chr(65+m) + s
    return ('' if crel else '$') + s + ('' if rrel else '$') + str(rw+1)

def _ref(rw, colf, base=None, rel=False):
    """PtgRef*: coords are ABSOLUTE. PtgRefN/PtgAreaN (rel=True): signed offsets from base."""
    col = colf & 0x3FFF
    crel = bool(colf & 0x4000); rrel = bool(colf & 0x8000)
    if rel and base is not None:
        br, bc = base
        if rrel:
            d = rw - 0x100000 if rw >= 0x80000 else rw
            rw = br + d
        if crel:
            d = col - 0x4000 if col >= 0x2000 else col
            col = bc + d
    return _a1(col & 0x3FFF, rw & 0xFFFFF, crel, rrel)

def parse(rgce, ctx, base=None):
    st = []
    p = 0; n = len(rgce)
    def pop(k):
        nonlocal st
        a = st[-k:] if k else []
        del st[len(st)-k:]
        return a
    while p < n:
        pt = rgce[p]; p += 1
        b = pt & 0x1F
        if pt == 0x19:   # PtgAttr
            g = rgce[p]; p += 1
            if g & 0x04:  # choose
                (cc,) = struct.unpack_from('<H', rgce, p); p += 2 + 2*(cc+1)
            else:
                p += 2
            if g & 0x10 and st:   # PtgAttrSum: SUM() de un solo argumento
                st[-1] = 'SUM(' + st[-1] + ')'
            continue
        if pt == 0x18:
            p += 1 + 4 if rgce[p] == 0x01 else 1+4
            continue
        if pt == 0x1E:
            (v,) = struct.unpack_from('<H', rgce, p); p += 2; st.append(str(v))
        elif pt == 0x1F:
            (v,) = struct.unpack_from('<d', rgce, p); p += 8; st.append(repr(v))
        elif pt == 0x17:
            if p+2 > n: st.append('<?STR>'); break
            s, p = rd_xlwstr_16(rgce, p); st.append('"'+s.replace('"','""')+'"')
        elif pt == 0x1D:
            v = rgce[p]; p += 1; st.append('TRUE' if v else 'FALSE')
        elif pt == 0x1C:
            v = rgce[p]; p += 1
            st.append({0:'#NULL!',7:'#DIV/0!',15:'#VALUE!',23:'#REF!',29:'#NAME?',36:'#NUM!',42:'#N/A'}.get(v,'#ERR'))
        elif pt == 0x16:
            st.append('')
        elif pt == 0x15:
            if st: st[-1] = '(' + st[-1] + ')'
        elif pt in (0x03,0x04,0x05,0x06,0x07,0x08,0x09,0x0A,0x0B,0x0C,0x0D,0x0E,0x0F,0x10,0x11):
            op = {3:'+',4:'-',5:'*',6:'/',7:'^',8:'&',9:'<',10:'<=',11:'=',12:'>=',13:'>',14:'<>',
                  15:' ',16:',',17:':'}[pt]
            a = pop(2)
            if len(a) == 2: st.append(a[0]+op+a[1])
        elif pt == 0x12:
            a = pop(1); st.append('+'+a[0] if a else '+')
        elif pt == 0x13:
            a = pop(1); st.append('-'+a[0] if a else '-')
        elif pt == 0x14:
            a = pop(1); st.append(a[0]+'%' if a else '%')
        elif b == 0x01 and pt in (0x21,0x41,0x61):
            (i,) = struct.unpack_from('<H', rgce, p); p += 2
            nm = _fname(i)
            ar = ARITY.get(i, 1)
            if ar < 0: ar = 1
            a = pop(ar); st.append(f'{nm}({",".join(a)})')
        elif b == 0x02 and pt in (0x22,0x42,0x62):
            cp = rgce[p]; p += 1
            (i,) = struct.unpack_from('<H', rgce, p); p += 2
            i &= 0x7FFF
            if i == 255:
                a = pop(cp)
                nm = a[0].strip('"') if a else '?'
                st.append(f'{nm}({",".join(a[1:])})')
            elif i == 0xFF or i == 186:
                a = pop(cp); st.append(f'FUNC{i}({",".join(a)})')
            else:
                a = pop(cp); st.append(f'{_fname(i)}({",".join(a)})')
        elif b == 0x03 and pt in (0x23,0x43,0x63):
            (i,) = struct.unpack_from('<I', rgce, p); p += 4
            st.append(ctx.names[i-1] if 0 < i <= len(ctx.names) else f'NAME{i}')
        elif b == 0x04 and pt in (0x24,0x44,0x64):
            rw, cf = struct.unpack_from('<IH', rgce, p); p += 6
            st.append(_ref(rw, cf))
        elif b == 0x05 and pt in (0x25,0x45,0x65):
            r1,r2,c1,c2 = struct.unpack_from('<IIHH', rgce, p); p += 12
            st.append(_ref(r1,c1)+':'+_ref(r2,c2))
        elif b == 0x1A and pt in (0x3A,0x5A,0x7A):
            (ix,) = struct.unpack_from('<H', rgce, p); p += 2
            rw, cf = struct.unpack_from('<IH', rgce, p); p += 6
            st.append(ctx.sheetref(ix)+_ref(rw, cf))
        elif b == 0x1B and pt in (0x3B,0x5B,0x7B):
            (ix,) = struct.unpack_from('<H', rgce, p); p += 2
            r1,r2,c1,c2 = struct.unpack_from('<IIHH', rgce, p); p += 12
            st.append(ctx.sheetref(ix)+_ref(r1,c1)+':'+_ref(r2,c2))
        elif b == 0x19 and pt in (0x39,0x59,0x79):
            (ix,) = struct.unpack_from('<H', rgce, p); p += 2
            (i,) = struct.unpack_from('<I', rgce, p); p += 4
            st.append(ctx.sheetref(ix)+(ctx.names[i-1] if 0 < i <= len(ctx.names) else f'NAME{i}'))
        elif pt in (0x20,0x40,0x60):  # PtgArray
            p += 14; st.append('{ARRAY}')
        elif pt in (0x2C,0x4C,0x6C):  # PtgRefN
            rw, cf = struct.unpack_from('<IH', rgce, p); p += 6
            st.append(_ref(rw, cf, base, True))
        elif pt in (0x2D,0x4D,0x6D):  # PtgAreaN
            r1,r2,c1,c2 = struct.unpack_from('<IIHH', rgce, p); p += 12
            st.append(_ref(r1,c1,base,True)+':'+_ref(r2,c2,base,True))
        elif pt in (0x2A,0x4A,0x6A,0x2B,0x4B,0x6B):  # RefErr / AreaErr
            p += 6 if pt in (0x2A,0x4A,0x6A) else 12
            st.append('#REF!')
        elif pt in (0x3C,0x5C,0x7C,0x3D,0x5D,0x7D):
            p += 6 if pt in (0x3C,0x5C,0x7C) else 12
            st.append('#REF!')
        elif pt == 0x00:
            continue
        else:
            st.append(f'<?{pt:02X}>'); break
    return st[-1] if st else ''

def rd_xlwstr_16(buf, off):
    (ln,) = struct.unpack_from('<H', buf, off); off += 2
    s = buf[off:off+2*ln].decode('utf-16-le','replace')
    return s, off+2*ln
