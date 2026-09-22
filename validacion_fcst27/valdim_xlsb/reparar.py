# -*- coding: utf-8 -*-
"""Repara el libro que el usuario modifico: conserva su disposicion y solo
 (1) cambia SUM(_xlfn.SINGLE(rango)) por SUM(rango) con el rango como referencia,
 (2) cambia Val_Resumen!E7:E26 (#REF! porque se borro la columna de Val_Ramo) por ABS(D)<0.005,
 (3) recalcula el valor guardado de todas las formulas de las hojas Val_* (el libro esta en calculo manual).
 Todo lo demas se copia byte a byte."""
import zipfile, struct, shutil, subprocess, os, tempfile, pickle, sys
from biff import sheet_map, colrow
from xlsbw import rec, wstr
import fmla, dump, evaluador

SRC, TMP, DST = 'USR.xlsb', 'TMP.xlsb', 'FCST_2027_Cesion.xlsb'
H = ['Val_Resumen','Val_Ramo','Val_LN','Val_Region','Val_TRea']
V3 = '../v3/'

def records_raw(buf):
    p = 0; n = len(buf)
    while p < n:
        s = p; b = buf[p]; p += 1
        rid = b & 0x7F
        if b & 0x80: b2 = buf[p]; p += 1; rid |= (b2 & 0x7F) << 7
        sz = 0; sh = 0
        for _ in range(4):
            c = buf[p]; p += 1; sz |= (c & 0x7F) << sh; sh += 7
            if not (c & 0x80): break
        yield rid, buf[p:p+sz], buf[s:p+sz]
        p += sz

def partir(rid, pl):
    "devuelve (hdr8, grbit2, tail) de un registro de formula"
    if rid == 9:  o = 16
    elif rid in (10, 11): o = 9
    elif rid == 8:
        (ln,) = struct.unpack_from('<I', pl, 8); o = 12 + 2*ln
    return pl[:8], pl[o:o+2], pl[o+2:]

def rgce_de(tail):
    (cce,) = struct.unpack_from('<I', tail, 0); return tail[4:4+cce], tail[4+cce:]

def fix_single(g):
    ok = (len(g) == 26 and g[0] == 0x23 and g[5] == 0x25 and g[18:22] == b'\x42\x02\xff\x00' and g[22:26] == b'\x42\x01\x04\x00')
    return (g[5:18] + b'\x42\x01\x04\x00') if ok else None

def fix_cuadra(r0):
    "ABS(D{fila})<0.005, referencia relativa a la Diferencia de Ramo en la misma fila"
    return struct.pack('<BIH', 0x44, r0, 3 | 0x4000 | 0x8000) + struct.pack('<BH', 0x41, 24) + struct.pack('<Bd', 0x1F, 0.005) + b'\x09'

def reescribir(src, dst, cambios_rgce, valores):
    """cambios_rgce[h][(r,c)] = rgce nuevo; valores[h][(r,c)] = valor (float/bool/str) o None para no tocar"""
    z = zipfile.ZipFile(src); SM = {n:p for n,p in sheet_map(src)}
    partes = {}; stats = {}
    for h in H:
        out = bytearray(); row = 0; nc = 0
        for rid, pl, raw in records_raw(z.read(SM[h])):
            if rid == 0: (row,) = struct.unpack_from('<I', pl, 0)
            if rid in (8,9,10,11):
                (col,) = struct.unpack_from('<I', pl, 0); k = (row, col)
                g_new = cambios_rgce.get(h, {}).get(k); v_new = valores.get(h, {}).get(k, None)
                if g_new is not None or v_new is not None:
                    hdr, grbit, tail = partir(rid, pl)
                    g, resto = rgce_de(tail)
                    if g_new is not None: tail = struct.pack('<I', len(g_new)) + g_new + resto
                    if v_new is None:
                        nrid, val = rid, pl[8:len(pl)-len(grbit)-len(partir(rid,pl)[2])]
                    elif isinstance(v_new, bool): nrid, val = 10, bytes([1 if v_new else 0])
                    elif isinstance(v_new, float): nrid, val = 9, struct.pack('<d', v_new)
                    elif isinstance(v_new, str): nrid, val = 8, wstr(v_new)
                    else: raise TypeError(v_new)
                    out += rec(nrid, hdr + val + grbit + tail); nc += 1
                    continue
            out += raw
        partes[SM[h]] = bytes(out); stats[h] = nc
    z.close()
    shutil.copyfile(src, dst)
    with tempfile.TemporaryDirectory() as td:
        for nombre, data in partes.items():
            p = os.path.join(td, nombre); os.makedirs(os.path.dirname(p), exist_ok=True); open(p,'wb').write(data)
        r = subprocess.run(['zip', '-X', '-D', '-q', os.path.abspath(dst)] + list(partes), cwd=td, capture_output=True, text=True)
        if r.returncode: raise RuntimeError(r.stderr)
    return stats

def main():
    # ---------- fase A: formulas ----------
    z = zipfile.ZipFile(SRC); SM = {n:p for n,p in sheet_map(SRC)}
    cambios = {h: {} for h in H}; malos = []
    for h in H:
        row = 0
        for rid, pl, raw in records_raw(z.read(SM[h])):
            if rid == 0: (row,) = struct.unpack_from('<I', pl, 0); continue
            if rid not in (8,9,10,11): continue
            (col,) = struct.unpack_from('<I', pl, 0)
            g, _ = rgce_de(partir(rid, pl)[2])
            if g[:1] == b'\x23' and b'\x42\x02\xff\x00' in g:
                ng = fix_single(g)
                if ng is None: malos.append((h, colrow(row,col), g.hex()))
                else: cambios[h][(row,col)] = ng
            elif g[:1] in (b'\x3c', b'\x5c', b'\x7c', b'\x2a', b'\x4a', b'\x6a'):
                if h == 'Val_Resumen' and col == 4 and 6 <= row <= 25: cambios[h][(row,col)] = fix_cuadra(row)
                else: malos.append((h, colrow(row,col), g.hex()))
    z.close()
    if malos: print('PATRONES INESPERADOS:', malos[:5]); sys.exit(1)
    print('formulas a corregir:', {h: len(v) for h, v in cambios.items()})
    reescribir(SRC, TMP, cambios, {})

    # ---------- fase B: recalculo ----------
    ctx = fmla.Ctx(TMP); S = dump.sst(TMP); SMt = {n:p for n,p in sheet_map(TMP)}
    CEL = {}; FORM = {}
    for h in H:
        CEL[h] = {}; FORM[h] = {}
        for r,c,v,f in dump.cells(TMP, SMt[h], ctx, S):
            if f: FORM[h][(r,c)] = f; CEL[h][(r,c)] = (None, f)
            else: CEL[h][(r,c)] = (v, None)
    rotas = [(h,k,f) for h in H for k,f in FORM[h].items() if 'SINGLE' in f or '#REF' in f or '<?' in f or 'FUNC' in f]
    if rotas: print('QUEDAN FORMULAS ROTAS:', rotas[:5]); sys.exit(1)
    F = evaluador.Fuentes(TMP, V3+'ctamens_full.pkl', V3+'celdas_ref.pkl')
    E = evaluador.Evaluador(F, CEL)
    for it in range(60):
        cambio = 0
        for h in H:
            for k, f in FORM[h].items():
                try: v = E.evaluar(h, f)
                except ValueError: v = None
                if isinstance(v, int) and not isinstance(v, bool): v = float(v)
                old = CEL[h][k][0]
                if old != v and not (isinstance(old,float) and isinstance(v,float) and abs(old-v) < 1e-9): cambio += 1
                CEL[h][k] = (v, f)
        if cambio == 0: break
    pend = [(h, colrow(*k)) for h in H for k in FORM[h] if CEL[h][k][0] is None]
    print(f'recalculo: {it+1} pasadas; formulas sin valor: {len(pend)} {pend[:5]}')
    if pend: sys.exit(1)
    norm = lambda v: 0.0 if (isinstance(v, float) and v == 0.0) else v      # sin -0.0, como escribe Excel
    valores = {h: {k: norm(CEL[h][k][0]) for k in FORM[h]} for h in H}
    st = reescribir(SRC, DST, cambios, valores)
    os.remove(TMP)
    pickle.dump(dict(CEL=CEL, FORM=FORM, cambios={h: sorted(v) for h,v in cambios.items()}), open('reparado.pkl','wb'))
    print('registros de formula reescritos:', st)

if __name__ == '__main__':
    main()
