# -*- coding: utf-8 -*-
"""Evaluador de las formulas de las hojas Val_* con SUMIFS generico sobre CtaMens."""
import re, pickle, collections
import pandas as pd
import fmla, dump
from biff import colrow, sheet_map

TEXTO = {'B','C','D','E','R'}          # columnas de CtaMens que se comparan como texto

def col0(letters):
    n = 0
    for ch in letters: n = n*26 + ord(ch)-64
    return n-1
def a1(ref):
    m = re.match(r'^\$?([A-Z]+)\$?(\d+)$', ref); return int(m.group(2))-1, col0(m.group(1))

class Base:
    """CtaMens como DataFrame con columnas por letra de Excel."""
    def __init__(self, df):
        self.df = df; self.cache = {}
    def sumifs(self, scol, crit):
        cols = tuple(c for c, _ in crit)
        key = (scol, cols)
        if key not in self.cache:
            self.cache[key] = self.df.groupby(list(cols))[scol].sum().to_dict()
        vals = tuple(v for _, v in crit)
        if len(vals) == 1: vals = vals[0]
        return float(self.cache[key].get(vals, 0.0))

class Hojas:
    def __init__(self, xlsb, nombres, ref_pkl=None):
        ctx = fmla.Ctx(xlsb); S = dump.sst(xlsb); SM = {n:p for n,p in sheet_map(xlsb)}
        self.v = {}
        for h in nombres:
            self.v[h] = {(r,c): v for r,c,v,f in dump.cells(xlsb, SM[h], ctx, S)}
        if ref_pkl:
            R = pickle.load(open(ref_pkl,'rb'))
            self.v['2_Reservas'] = {k: v[0] for k, v in R['2_Reservas'].items()}
            if 'Parámetros' not in self.v: self.v['Parámetros'] = R['Parametros']

class Evaluador:
    def __init__(self, base, hojas, CEL, xev=0.0):
        self.B = base; self.H = hojas; self.CEL = CEL; self.XEV = xev
    def r3(self, hoja, ref):
        r, c = a1(ref)
        if hoja in self.CEL: v = self.CEL[hoja].get((r,c), (None,None))[0]
        elif hoja in self.H.v: v = self.H.v[hoja].get((r,c))
        else: raise KeyError(hoja)
        if isinstance(v, str) and v.startswith('#'): raise ValueError('error en ' + hoja + '!' + ref)
        return v
    def num(self, v):
        if v is None or v == '': return 0.0
        if isinstance(v, bool): return float(v)
        if isinstance(v, str): raise ValueError('texto en operacion')
        return float(v)
    def rango(self, hoja, rng):
        a, b = rng.split(':'); (r1,c1), (r2,c2) = a1(a), a1(b); out = []
        for r in range(r1, r2+1):
            for c in range(c1, c2+1):
                v = self.r3(hoja, colrow(r,c))
                if isinstance(v, (int,float)) and not isinstance(v, bool): out.append(float(v))
        return out
    def evaluar(self, hoja, f):
        ev = self; s = f; hold = []
        def keep(t): hold.append(t); return f'__H{len(hold)-1}__'
        def sif(args):
            toks = [t.strip() for t in args.split(',')]
            sc = re.match(r"^CtaMens!\$([A-Z]+)\$4:\$[A-Z]+\$201234$", toks[0]).group(1)
            crit = []
            for k in range(1, len(toks), 2):
                cc = re.match(r"^CtaMens!\$([A-Z]+)\$4:\$[A-Z]+\$201234$", toks[k]).group(1)
                t = toks[k+1]
                if re.match(r'^-?\d+(\.\d+)?$', t): v = float(t)
                elif t.startswith('"'): v = t.strip('"')
                else: v = self.r3(hoja, t)
                if cc in TEXTO: v = (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v))
                else: v = float(v)
                if cc == 'A': v = int(v)
                crit.append((cc, v))
            return self.B.sumifs(sc, crit)
        s = re.sub(r'SUMIFS\(([^()]*)\)', lambda m: keep(repr(sif(m.group(1)))), s)
        AGG = {'SUM': sum, 'MAX': max, 'MIN': min}
        for fn, g in AGG.items():
            s = re.sub(fn + r"\('?([A-Za-z0-9_]+)'?!(\$?[A-Z]+\$?\d+:\$?[A-Z]+\$?\d+)\)",
                       lambda m, g=g: keep(repr(g(self.rango(m.group(1), m.group(2)) or [0.0]))), s)
            s = re.sub(fn + r'\((\$?[A-Z]+\$?\d+:\$?[A-Z]+\$?\d+)\)',
                       lambda m, g=g: keep(repr(g(self.rango(hoja, m.group(1)) or [0.0]))), s)
        s = s.replace('ABS(', 'abs(').replace('xEvCat', repr(self.XEV))
        s = re.sub(r"'([^']+)'!(\$?[A-Z]+\$?\d+)", lambda m: keep(f'ev.num(ev.r3("{m.group(1)}","{m.group(2)}"))'), s)
        s = re.sub(r"([A-Za-z0-9_]+)!(\$?[A-Z]+\$?\d+)", lambda m: keep(f'ev.num(ev.r3("{m.group(1)}","{m.group(2)}"))'), s)
        s = re.sub(r'(?<![A-Za-z0-9_"])(\$?[A-Z]{1,2}\$?\d+)(?![\d"])', lambda m: f'ev.num(ev.r3("{hoja}","{m.group(1)}"))', s)
        for i, t in enumerate(hold): s = s.replace(f'__H{i}__', t)
        return eval(s, {'ev': ev, 'abs': abs})
