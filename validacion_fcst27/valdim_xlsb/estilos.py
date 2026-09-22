# -*- coding: utf-8 -*-
"""Anexa fuentes, rellenos, bordes y xfs a xl/styles.bin copiando el formato de los registros existentes."""
import struct
from biff import records
from xlsbw import rec, wstr

def color_rgb(hexrgb):
    r, g, b = int(hexrgb[0:2],16), int(hexrgb[2:4],16), int(hexrgb[4:6],16)
    return bytes([0x05, 0xFF, 0, 0, r, g, b, 0xFF])           # fValidRGB=1, xColorType=2 (RGB)
COLOR_AUTO_BG = bytes.fromhex('03400000000000ff')             # igual que los rellenos del libro
COLOR_NONE    = bytes.fromhex('0140000000000000')             # como los bordes dg=0 del libro

def font(pt, bold=False, italic=False, rgb='000000', name='Arial'):
    grbit = 0x0002 if italic else 0
    return rec(43, struct.pack('<HHHHBBBB', int(pt*20), grbit, 700 if bold else 400, 0, 0, 2, 0, 0)
                   + color_rgb(rgb) + b'\x00' + wstr(name))

def fill_solid(rgb):
    return rec(45, struct.pack('<I', 1) + color_rgb(rgb) + COLOR_AUTO_BG + b'\x00'*48)

def border_thin(rgb='D4D4D4'):
    lado = bytes([1, 0]) + color_rgb(rgb)
    nada = bytes([0, 0]) + COLOR_NONE
    return rec(46, b'\x00' + lado*4 + nada)

def xf(fmt=0, font=0, fill=0, border=0, alc=0, alcv=2, wrap=False):
    flags = (alc & 7) | ((alcv & 7) << 3) | (0x40 if wrap else 0) | 0x1000       # fLocked
    attr = (1 if fmt else 0) | (2 if font else 0) | 4 | (8 if border else 0) | (16 if fill else 0)
    return rec(47, struct.pack('<HHHHHBBHH', 0, fmt, font, fill, border, 0, 0, flags, attr))

def agregar(styles_bin, fuentes, rellenos, bordes, xfs):
    """fuentes/rellenos/bordes/xfs: listas de registros ya serializados. Devuelve (bytes, indices base)."""
    base = {}
    out = bytearray(); counts = {}
    # primera pasada: contar
    for rid, pl in records(styles_bin):
        if rid in (611, 603, 613, 617): counts[rid] = struct.unpack_from('<I', pl, 0)[0]
    base['font'] = counts[611]; base['fill'] = counts[603]; base['border'] = counts[613]; base['xf'] = counts[617]
    add = {611: (612, fuentes), 603: (604, rellenos), 613: (614, bordes), 617: (618, xfs)}
    pend = None
    for rid, pl in records(styles_bin):
        if rid in add:
            n = struct.unpack_from('<I', pl, 0)[0] + len(add[rid][1])
            pl = struct.pack('<I', n) + pl[4:]
            pend = add[rid]
        if pend and rid == pend[0]:
            for r in pend[1]: out += r
            pend = None
        out += rec(rid, pl)
    return bytes(out), base

# ---------- paleta de la validacion ----------
VERDE_OSC, VERDE_CLARO, GRIS, AMARILLO, GRIS_TXT, GRIS_BORDE = '1A5632', 'EEF6F0', 'EAEAEA', 'FFF4CE', '555555', 'D4D4D4'

def paleta(styles_bin):
    fuentes = [font(14, bold=True, rgb=VERDE_OSC),      # +0 titulo
               font(9,  rgb=GRIS_TXT),                  # +1 subtitulo / observacion
               font(9,  bold=True, rgb='FFFFFF'),       # +2 encabezado blanco
               font(9,  bold=True, rgb='000000'),       # +3 negrita
               font(9,  rgb='000000'),                  # +4 normal
               font(8,  italic=True, rgb='777777')]     # +5 nota
    rellenos = [fill_solid(VERDE_OSC), fill_solid(VERDE_CLARO), fill_solid(GRIS), fill_solid(AMARILLO)]
    bordes = [border_thin(GRIS_BORDE)]
    # primero calculamos las bases
    _, base = agregar(styles_bin, [], [], [], [])
    F = lambda i: base['font'] + i
    FI = lambda i: base['fill'] + i
    BO = base['border']
    NUM = 4                                              # '#,##0.00' (formato integrado)
    defs = [
     ('TIT',    dict(font=F(0))),
     ('SUB',    dict(font=F(1))),
     ('NOTA',   dict(font=F(5))),
     ('BAR',    dict(font=F(2), fill=FI(0), border=BO, alc=1, alcv=1)),
     ('BAR_C',  dict(font=F(2), fill=FI(0), border=BO, alc=2, alcv=1)),
     ('HDR',    dict(font=F(3), fill=FI(1), border=BO, alc=1, alcv=1)),
     ('HDR_C',  dict(font=F(3), fill=FI(2), border=BO, alc=2, alcv=1)),
     ('TXT',    dict(font=F(4), border=BO, alc=1)),
     ('OBS',    dict(font=F(1), border=BO, alc=1)),
     ('NUM',    dict(fmt=NUM, font=F(4), border=BO)),
     ('NUM_B',  dict(fmt=NUM, font=F(3), fill=FI(1), border=BO)),
     ('NUM_G',  dict(fmt=NUM, font=F(3), fill=FI(2), border=BO)),
     ('NUM_Y',  dict(fmt=NUM, font=F(3), fill=FI(3), border=BO)),
     ('LBL_B',  dict(font=F(3), fill=FI(1), border=BO, alc=1)),
     ('LBL_G',  dict(font=F(3), fill=FI(2), border=BO, alc=1)),
     ('LBL_Y',  dict(font=F(3), fill=FI(3), border=BO, alc=1)),
     ('BOOL',   dict(font=F(3), fill=FI(3), border=BO, alc=2)),
     ('MES',    dict(font=F(1), alc=2)),
     ('TXT_C',  dict(font=F(4), border=BO, alc=2)),
     ('TXT_B',  dict(font=F(3), alc=1)),
     ('NUM_S',  dict(fmt=NUM, font=F(4))),
    ]
    xfs = [xf(**kw) for _, kw in defs]
    nuevo, base = agregar(styles_bin, fuentes, rellenos, bordes, xfs)
    X = {nom: base['xf'] + i for i, (nom, _) in enumerate(defs)}
    return nuevo, X
