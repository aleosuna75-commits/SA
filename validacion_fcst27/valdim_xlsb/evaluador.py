# -*- coding: utf-8 -*-
"""Evalua las formulas de las hojas Val_* (texto decodificado) contra CtaMens y las hojas fuente."""
import re, pickle, collections
import fmla, dump
from biff import colrow, sheet_map

COLS = {'A':'A_mes','B':'B_cta','C':'C_ln','E':'E_reg','L':'L_tre','Q':'Q_monto','R':'R_ramo','W':'W_ced',
        'AA':'AA_xl','AB':'AB_recu','AC':'AC_evcat','AD':'AD_attcat','AE':'AE_sincatced','AF':'AF_gtos'}
AMT = ['Q_monto','W_ced','AA_xl','AB_recu','AC_evcat','AD_attcat','AE_sincatced','AF_gtos']

class Fuentes:
    def __init__(self, xlsb, ctamens_pkl, ref_pkl):
        d = pickle.load(open(ctamens_pkl,'rb')); self.REF = pickle.load(open(ref_pkl,'rb'))
        self.G1 = {}; self.G2 = {}
        for dc in ['R_ramo','C_ln','E_reg','L_tre']:
            self.G1[dc] = d.groupby([dc,'B_cta','A_mes'])[AMT].sum().to_dict('index')
            self.G2[dc] = d.groupby([dc,'A_mes'])[AMT].sum().to_dict('index')
        ctx = fmla.Ctx(xlsb); S = dump.sst(xlsb); SM = {n:p for n,p in sheet_map(xlsb)}
        self.otras = {}
        for h in ('CAT','Gastos','ValDim'):
            self.otras[h] = {(r,c): v for r,c,v,f in dump.cells(xlsb, SM[h], ctx, S)}

def col0(letters):
    n = 0
    for ch in letters: n = n*26 + ord(ch)-64
    return n-1
def a1(ref):
    m = re.match(r'^\$?([A-Z]+)\$?(\d+)$', ref); return int(m.group(2))-1, col0(m.group(1))

class Evaluador:
    def __init__(self, fuentes, CEL, xev=0.0):
        self.F = fuentes; self.CEL = CEL; self.XEV = xev; self.cache = {}
    def r3(self, hoja, ref):
        r, c = a1(ref); R = self.F.REF
        if hoja in ('Parámetros','Parametros'): v = R['Parametros'].get((r,c))
        elif hoja in ('ER','Inicio'): v = R[hoja].get((r,c))
        elif hoja == '2_Reservas': v = R['2_Reservas'].get((r,c),(None,None))[0]
        elif hoja in ('ER_ram','ER_ln','ER_reg','ER_tre'): v = R[hoja].get((r,c))
        elif hoja in self.F.otras: v = self.F.otras[hoja].get((r,c))
        elif hoja in self.CEL: v = self.CEL[hoja].get((r,c),(None,None))[0]
        else: raise KeyError(hoja)
        return v if isinstance(v,(int,float,bool,str)) else 0.0
    def num(self, v):
        if v is None or v == '' : return 0.0
        if isinstance(v, str) and v.startswith('#'): raise ValueError('error en referencia '+v)
        return v
    def rango(self, hoja, rng):
        a, b = rng.split(':'); (r1,c1), (r2,c2) = a1(a), a1(b); s = 0.0
        for r in range(r1, r2+1):
            for c in range(c1, c2+1):
                v = self.r3(hoja, colrow(r,c))
                if isinstance(v,(int,float)) and not isinstance(v,bool): s += v
                elif isinstance(v,str) and v.startswith('#'): raise ValueError('error en rango')
        return s
    def evaluar(self, hoja, f):
        ev = self; s = f; hold = []
        def keep(t): hold.append(t); return f'__H{len(hold)-1}__'
        def sif(args):
            toks = [t.strip() for t in args.split(',')]
            sc = re.match(r"^CtaMens!\$([A-Z]+)\$4:\$[A-Z]+\$201234$", toks[0]).group(1)
            crit = {}
            for k in range(1, len(toks), 2):
                cc = re.match(r"^CtaMens!\$([A-Z]+)\$4:\$[A-Z]+\$201234$", toks[k]).group(1)
                cv = toks[k+1]
                crit[cc] = float(cv) if re.match(r'^-?\d+(\.\d+)?$', cv) else self.num(self.r3(hoja, cv))
            dimcol = [c for c in crit if c in ('R','C','E','L')][0]; dc = COLS[dimcol]
            mes = int(crit['A']); mb = crit[dimcol]
            if dc == 'L_tre': mb = float(mb)
            row = self.F.G1[dc].get((mb, str(int(crit['B'])), mes)) if 'B' in crit else self.F.G2[dc].get((mb, mes))
            return float(row[COLS[sc]]) if row else 0.0
        s = re.sub(r'SUMIFS\(([^()]*)\)', lambda m: keep(repr(sif(m.group(1)))), s)
        s = re.sub(r"SUM\('?([A-Za-z0-9_]+)'?!(\$?[A-Z]+\$?\d+:\$?[A-Z]+\$?\d+)\)", lambda m: keep(repr(self.rango(m.group(1), m.group(2)))), s)
        s = re.sub(r'SUM\((\$?[A-Z]+\$?\d+:\$?[A-Z]+\$?\d+)\)', lambda m: keep(repr(self.rango(hoja, m.group(1)))), s)
        s = s.replace('ABS(', 'abs(').replace('xEvCat', repr(self.XEV))
        s = re.sub(r"'([^']+)'!(\$?[A-Z]+\$?\d+)", lambda m: keep(f'ev.num(ev.r3("{m.group(1)}","{m.group(2)}"))'), s)
        s = re.sub(r"([A-Za-z0-9_]+)!(\$?[A-Z]+\$?\d+)", lambda m: keep(f'ev.r3("{m.group(1)}","{m.group(2)}")'), s)
        s = re.sub(r'(?<![A-Za-z0-9_"])(\$?[A-Z]{1,2}\$?\d+)(?![\d"])', lambda m: f'ev.num(ev.r3("{hoja}","{m.group(1)}"))', s)
        for i, t in enumerate(hold): s = s.replace(f'__H{i}__', t)
        return eval(s, {'ev': ev, 'abs': abs})
