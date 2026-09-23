# -*- coding: utf-8 -*-
"""Reparte en CtaMens (2027) el CAT y los Gastos Generales con la misma regla que trae
Integracion2026_Dim_10:
  AD AttritionalCat      = CAT!H14:S25 (Cebe x territorio x mes) en proporcion a MONTO de los renglones de prima (B=61)
  AE SiniestrosCatCedidos = AD x %cesion de CAT!Z38 (Ultramar R05), Z39 (A071 resto), Z40 (A073 resto)
  AC EventosCat          = CAT!H49:S66 (Cebe x territorio x mes), misma proporcion
  AF GastosGenerales     = Gastos!C12:N12 (mes) en proporcion a MONTO de todos los renglones de prima del mes
Caso sin prima en (Cebe, territorio, mes): se reparte en el mismo mes y Cebe entre los territorios
de la misma clase de cesion (Ultramar = R05; resto = no-Ultramar)."""
import pickle, collections
import pandas as pd, numpy as np
import fmla, dump
from biff import sheet_map

def cargar(F, pkl):
    N = pickle.load(open(pkl, 'rb'))
    for c in ['Q']: N[c] = pd.to_numeric(N[c], errors='coerce').fillna(0.0)
    ctx = fmla.Ctx(F); S = dump.sst(F); SM = {n:p for n,p in sheet_map(F)}
    CAT = {(r,c): v for r,c,v,f in dump.cells(F, SM['CAT'], ctx, S)}
    GAS = {(r,c): v for r,c,v,f in dump.cells(F, SM['Gastos'], ctx, S)}
    return N, CAT, GAS

def num(v): return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0

def repartir(N, CAT, GAS, anio=2027):
    meses = [anio*100 + j for j in range(1, 13)]
    P = N[N['B'] == '61'][['_fila','A','D','E','Q']].copy()
    idx_g = {k: v.index.values for k, v in P.groupby(['D','E','A'])}
    idx_m = {k: v.index.values for k, v in P.groupby(['A'])}
    Q = P['Q']
    ac = collections.defaultdict(float); ad = collections.defaultdict(float)
    ae = collections.defaultdict(float); af = collections.defaultdict(float)
    tasa = {'U': num(CAT.get((37,25))), 'A071000000': num(CAT.get((38,25))), 'A073000000': num(CAT.get((39,25)))}
    clase = lambda t: 'U' if t == 'R05' else 'N'
    respaldo = []
    def asigna(dest, importe, ids, extra=None):
        q = Q.loc[ids]; s = q.sum()
        for i, qi in zip(ids, q.values):
            dest[i] += importe * qi / s
            if extra is not None: extra[0][i] += importe * qi / s * extra[1]
    def bloque(r1, r2, dest, con_cesion):
        for r in range(r1, r2+1):
            ce, te = CAT.get((r-1,2)), CAT.get((r-1,4))
            if not ce: continue
            for j, m in enumerate(meses):
                a = num(CAT.get((r-1, 7+j)))
                if a == 0: continue
                ids = idx_g.get((ce, te, m))
                if ids is None or abs(Q.loc[ids].sum()) < 1e-9:
                    pool = [i for (c2, t2, m2), v in idx_g.items() if c2 == ce and m2 == m and clase(t2) == clase(te) for i in v]
                    ids = np.array(pool)
                    respaldo.append(dict(bloque=('attritional' if dest is ad else 'eventos'), fila_cat=r, cebe=ce, territorio=te, mes=m, importe=a,
                                         repartido_en=sorted({P.loc[i,'E'] for i in pool})))
                    if len(ids) == 0 or abs(Q.loc[ids].sum()) < 1e-9: raise RuntimeError(f'sin base para {ce} {te} {m}')
                rate = (tasa['U'] if te == 'R05' else tasa[ce]) if con_cesion else None
                asigna(dest, a, ids, (ae, rate) if con_cesion else None)
    bloque(14, 25, ad, True)
    bloque(49, 66, ac, False)
    for j, m in enumerate(meses):
        a = num(GAS.get((11, 2+j)))
        ids = idx_m.get(m) if (m,) not in idx_m else idx_m[(m,)]
        if ids is None: ids = idx_m.get((m,))
        asigna(af, a, ids)
    filas = collections.defaultdict(dict)
    for col, dest in ((28, ac), (29, ad), (30, ae), (31, af)):
        for i, v in dest.items():
            filas[int(P.loc[i, '_fila'])][col] = v
    return dict(filas), respaldo, tasa

if __name__ == '__main__':
    N, CAT, GAS = cargar('NUESTRO.xlsb', 'nuestro_ctamens_limpio.pkl')
    filas, respaldo, tasa = repartir(N, CAT, GAS)
    pickle.dump(dict(filas=filas, respaldo=respaldo, tasa=tasa), open('reparto.pkl','wb'))
    tot = collections.defaultdict(float)
    for f, d in filas.items():
        for c, v in d.items(): tot[c] += v
    print('renglones con importe:', len(filas), '| tasas de cesion:', tasa)
    print('totales AC %.2f  AD %.2f  AE %.2f  AF %.2f' % (tot[28], tot[29], tot[30], tot[31]))
    print('CAT!T68 %.2f  CAT!T27 %.2f  CAT!T41 %.2f  Gastos %.2f' % (num(CAT.get((67,19))), num(CAT.get((26,19))), num(CAT.get((40,19))),
          sum(num(GAS.get((11,2+j))) for j in range(12))))
    print('casos de respaldo:')
    for x in respaldo: print('   ', x)
