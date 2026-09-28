# -*- coding: utf-8 -*-
"""Cifras para llenar 05_FCST_2027.xlsx desde las vistas ER del libro de Cesion.

Cada renglon de ER_ln / ER_ram / ER_reg / ER_tre se evalua para cada miembro con la
misma formula de la vista (como si el selector A6 se pusiera en cada uno), en USD y en
MXN. MXN es lo que da la vista con xMonEEFF = "MXN": cada flujo mensual se multiplica por
'Parámetros'!F3:Q3 y se acumula. El USD se cruza contra los valores guardados de las
hojas Val_* (que ya reproducen la vista) para asegurar que el motor es el mismo.

Tambien evalua el ER global en MXN (hasta Resultado de Operacion y las otras reservas,
mas las filas financieras que no dependen de una referencia circular) y la columna D
(real 2025) de cada vista por miembro.

Entrada: ctamens_v3.pkl y celdas_v3.pkl (cargar_v3.py). Salida: datos05.pkl."""
import pickle, re, math, sys
import numpy as np, pandas as pd

d = pickle.load(open('ctamens_v3.pkl', 'rb'))
CEL = pickle.load(open('celdas_v3.pkl', 'rb'))
NM = 12; MESES = list(range(202701, 202713))

def val(hoja, r, c):
    v = CEL[hoja].get((r, c), (None, None))[0]
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0

TC = [val('Parámetros', 2, 5+j) for j in range(NM)]              # 'Parámetros'!F3:Q3
TASA_CG = [val('Parámetros', 9, 5+j) for j in range(NM)]         # F10:Q10
TASA_RO = [val('Parámetros', 10, 5+j) for j in range(NM)]        # F11:Q11
TCC = [val('Parámetros', 7, 4+j) for j in range(NM+1)]           # E8:Q8 (TC cierre)
XEVCAT = val('Inicio', 12, 2)                                    # Inicio!C13
UNO = [1.0]*NM
assert all(t > 10 for t in TC), TC

def acum(x): return list(np.cumsum(x))

# ---------------- vistas por miembro ----------------
DIM = {
 'RAMO':  dict(vista='ER_ram', col='R_ramo', key_col=20, tipo='texto', hoja_val='Val_Ramo',
               t12=[(65,78)], t13=[(84,97)], t18=[(103,116)], t25=[(121,134)]),
 'LN':    dict(vista='ER_ln',  col='C_ln',   key_col=21, tipo='texto', hoja_val='Val_LN',
               t12=[(6,13)],  t13=[(18,25)],  t18=[(31,38)],  t25=[(45,52)]),
 'REGION':dict(vista='ER_reg', col='E_reg',  key_col=21, tipo='texto', hoja_val='Val_Region',
               t12=[(147,152),(169,174)], t13=[(158,163),(180,185)], t18=[(191,196)], t25=[(203,208)]),
 'TREA':  dict(vista='ER_tre', col='L_tre',  key_col=21, tipo='numero', hoja_val='Val_TRea',
               t12=[(220,222),(236,238)], t13=[(228,230),(244,246)], t18=[(252,254)], t25=[(261,263)]),
}
LINEAS = [9,10,11,12,13,16,17,18,19,20,23,24,25,26,27,28,31,32,33,35]
RES = CEL['2_Reservas']
def rv(r, c):
    v = RES.get((r, c), (None, None))[0]
    return float(v) if isinstance(v, (int, float)) else 0.0

def clave(v, tipo): return float(v) if tipo == 'numero' else str(v)

def filas_miembro(bloques, key_col, tipo, mb):
    out = []
    for r1, r2 in bloques:
        hit = None
        for r in range(r1, r2+1):
            k = RES.get((r, key_col), (None, None))[0]
            if k is not None and clave(k, tipo) == mb: hit = r; break
        out.append(hit)
    return out

def evaluar(dim, mb, fx):
    cfg = DIM[dim]; sub = d[d[cfg['col']] == mb]
    def S(campo, cta=None):
        s = sub if cta is None else sub[sub.B_cta == str(cta)]
        g = s.groupby('A_mes')[campo].sum()
        return [float(g.get(m, 0.0)) for m in MESES]
    X = lambda serie: acum([a*f for a, f in zip(serie, fx)])
    m = {}
    m[9] = X([-v for v in S('Q_monto', 61)])
    m[10] = X([-v for v in S('W_ced', 61)])
    m[11] = [a-b for a, b in zip(m[9], m[10])]
    def reserva(bl):
        fr = filas_miembro(bl, cfg['key_col'], cfg['tipo'], mb)
        if all(f is None for f in fr): return None
        return X([sum(rv(f, 22+j) for f in fr if f is not None) for j in range(NM)])
    m[12] = reserva(cfg['t12']); m[13] = reserva(cfg['t13'])
    m[18] = reserva(cfg['t18']); m[25] = reserva(cfg['t25'])
    z = lambda v: v if v is not None else [0.0]*NM
    m[16] = [a-b for a, b in zip(m[9], z(m[12]))]
    q54, ac, ad = S('Q_monto', 54), S('AC_evcat'), S('AD_attcat')
    m[17] = X([a + b*XEVCAT + c for a, b, c in zip(q54, ac, ad)])
    m[19] = X(S('Q_monto', 53))
    m[20] = [a-(b+c+e) for a, b, c, e in zip(m[16], m[17], z(m[18]), m[19])]
    m[23] = [a-b for a, b in zip(m[11], z(m[13]))]
    w54, ae, ab = S('W_ced', 54), S('AE_sincatced'), S('AB_recu')
    m[24] = X([(a + b*XEVCAT + c) - (w + e - r*XEVCAT) for a, b, c, w, e, r in zip(q54, ac, ad, w54, ae, ab)])
    m[26] = X([a-b for a, b in zip(S('Q_monto', 53), S('W_ced', 53))])
    m[27] = X(S('AA_xl', 61))
    m[28] = [a-(b+c+e+f) for a, b, c, e, f in zip(m[23], m[24], z(m[25]), m[26], m[27])]
    m[31] = X(S('AF_gtos', 61))
    m[32] = [a*t for a, t in zip(m[10], TASA_CG)]
    m[33] = [a-b for a, b in zip(m[31], m[32])]
    m[35] = [a-b for a, b in zip(m[28], m[33])]
    return m

def miembros(dim):
    cfg = DIM[dim]; keys = []
    for r in range(cfg['t12'][0][0], cfg['t12'][0][1]+1):
        k = RES.get((r, cfg['key_col']), (None, None))[0]
        if k is not None: keys.append(clave(k, cfg['tipo']))
    reales = [clave(x, cfg['tipo']) for x in d[cfg['col']].dropna().unique()]
    return keys + sorted([x for x in set(reales) if x not in keys], key=str)

def leer_val(hoja):
    """{(linea, miembro): [12]} de los valores guardados de Val_x (meses en C:N)."""
    V = CEL[hoja]; out = {}; ln = None
    c0 = next(c for (r, c), (v, f) in V.items() if r == 3 and v == 202701.0)     # columna de enero
    for r in sorted({r for r, c in V}):
        a = V.get((r, 0), (None, None))[0]
        if isinstance(a, str):
            mt = re.match(r'^(\d+) · ', a)
            if mt: ln = int(mt.group(1)); continue
            if a in ('Miembro', 'Suma de los miembros', 'ER (global)', 'Diferencia (suma − ER)') or ln is None: continue
        if ln is None or a is None: continue
        vals = [V.get((r, c0+j), (None, None))[0] for j in range(NM)]
        if all(isinstance(x, (int, float)) for x in vals): out[(ln, a)] = [float(x) for x in vals]
    return out

VISTAS = {}
peor_global = 0.0
for dim, cfg in DIM.items():
    mbs = miembros(dim); ref = leer_val(cfg['hoja_val'])
    usd = {mb: evaluar(dim, mb, UNO) for mb in mbs}
    mxn = {mb: evaluar(dim, mb, TC) for mb in mbs}
    peor = 0.0; n = 0
    for (ln, mb), serie in ref.items():
        mine = usd[mb][ln]
        if mine is None: continue
        for j in range(NM):
            peor = max(peor, abs(mine[j] - serie[j])); n += 1
    faltan = [(ln, mb) for mb in mbs for ln in LINEAS if usd[mb][ln] is not None and (ln, mb) not in ref]
    print(f'{dim:<6} {len(mbs)} miembros {mbs}  celdas cruzadas con {cfg["hoja_val"]}: {n}  peor dif USD = {peor:.6f}  sin par: {len(faltan)}')
    peor_global = max(peor_global, peor)
    VISTAS[dim] = dict(miembros=mbs, usd=usd, mxn=mxn)
assert peor_global < 0.01, peor_global

# ---------------- selector vivo de cada vista (MXN = USD * TC por mes) ----------------
for dim, cfg in DIM.items():
    H = CEL[cfg['vista']]; sel = H.get((5, 0), (None, None))[0]
    sel = clave(sel, cfg['tipo']); u = VISTAS[dim]['usd'][sel]; por_fila = {}
    for ln in LINEAS:
        for j in range(NM):
            x = H.get((ln-1, 4+j), (None, None))[0]
            if isinstance(x, (int, float)) and u[ln] is not None:
                por_fila[ln] = max(por_fila.get(ln, 0.0), abs(x - u[ln][j]))
    malas = {ln: round(v, 2) for ln, v in por_fila.items() if v > 0.01}
    print(f'  vista {cfg["vista"]} A6={sel!r}: filas con dif vs valor guardado de la vista: {malas}')

# ---------------- ER global en MXN ----------------
def er_eval(fx):
    p = d
    def S(campo, cta=None):
        s = p if cta is None else p[p.B_cta == str(cta)]
        g = s.groupby('A_mes')[campo].sum()
        return [float(g.get(m, 0.0)) for m in MESES]
    X = lambda serie: acum([a*f for a, f in zip(serie, fx)])
    CAT = lambda fila: [val('CAT', fila-1, 7+j) for j in range(NM)]          # CAT!H:S
    RS = lambda fila: [rv(fila-1, 22+j) for j in range(NM)]                  # 2_Reservas!W:AH
    GS = lambda fila: [val('Gastos', fila-1, 2+j) for j in range(NM)]        # Gastos!C:N
    e = {}
    e[5] = X([-v for v in S('Q_monto', 61)]); e[6] = X([-v for v in S('W_ced', 61)])
    e[7] = [a-b for a, b in zip(e[5], e[6])]
    e[8] = X(RS(81)); e[9] = X(RS(100))
    e[11] = [a-b for a, b in zip(e[5], e[8])]
    e[13] = X([a+b+c for a, b, c in zip(S('Q_monto', 54), CAT(27), CAT(83))])
    e[14] = [0.0]*NM; e[15] = X(RS(118))
    e[12] = [a+b+c for a, b, c in zip(e[13], e[14], e[15])]
    e[17] = X(S('Q_monto', 53)); e[18] = [0.0]*NM; e[19] = [0.0]*NM
    e[16] = [a+b+c for a, b, c in zip(e[17], e[18], e[19])]
    e[20] = [a-b-c for a, b, c in zip(e[11], e[12], e[16])]
    e[32] = [a-b for a, b in zip(e[7], e[9])]
    e[22] = [a-b for a, b in zip(e[11], e[32])]
    e[24] = X([a+b+c for a, b, c in zip(S('W_ced', 54), CAT(41), CAT(84))])
    e[36] = X(RS(136))
    e[25] = [a-b for a, b in zip(e[15], e[36])]
    e[23] = [a+b for a, b in zip(e[24], e[25])]
    e[26] = X([a*XEVCAT for a in S('AB_recu')])
    e[28] = X(S('W_ced', 53)); e[29] = X([-v for v in S('AA_xl', 61)])
    e[27] = [a+b for a, b in zip(e[28], e[29])]
    e[30] = [a-b-c-f for a, b, c, f in zip(e[22], e[23], e[26], e[27])]
    e[34] = e[13]; e[35] = e[14]
    e[37] = [a+b for a, b in zip(e[24], e[26])]
    e[33] = [a+b+c-f for a, b, c, f in zip(e[34], e[35], e[36], e[37])]
    e[39] = e[17]; e[40] = e[18]; e[41] = e[19]; e[42] = e[28]; e[43] = [-v for v in e[29]]
    e[38] = [a+b+c-f+g for a, b, c, f, g in zip(e[39], e[40], e[41], e[42], e[43])]
    e[44] = [a-b-c for a, b, c in zip(e[32], e[33], e[38])]
    e[46] = X(GS(12)); e[47] = [0.0]*NM; e[48] = [0.0]*NM; e[49] = [0.0]*NM; e[51] = [0.0]*NM
    ced_mens = [e[6][0]] + [e[6][j]-e[6][j-1] for j in range(1, NM)]
    e[50] = acum([c*t for c, t in zip(ced_mens, TASA_CG)])
    e[52] = [a+b+c-(x+y+w) for a, b, c, x, y, w in zip(e[46], e[47], e[48], e[49], e[50], e[51])]
    e[53] = [a-b for a, b in zip(e[44], e[52])]
    e[55] = X(RS(280)); e[56] = X(RS(292))
    e[57] = [a+b for a, b in zip(e[55], e[56])]
    e[58] = [a-b for a, b in zip(e[53], e[57])]
    # financieras sin referencia circular
    y60 = val('ER', 59, 24)                                                  # ER!Y60 (= RIF!P231)
    e[60] = acum([y60/12]*NM)
    e[61] = [0.0]*NM; e[65] = [0.0]*NM; e[68] = [0.0]*NM
    e[64] = [val('ER', 63, 5+j) for j in range(NM)]                          # constantes y RIF!E22*RIF!K23 / RIF!E22 / RIF!F22, sin tipo de cambio
    e[66] = [78644000.0*(TCC[1+j] - TCC[0]) for j in range(NM)]
    e[69] = X([-v for v in GS(13)])
    e[79] = [a*t for a, t in zip(e[7], TASA_RO)]
    return e

ER_USD = er_eval(UNO); ER_MXN = er_eval(TC)

# cruce del ER evaluado en USD contra Val_Resumen / sumas de miembros (filas tecnicas)
MAPA = {9:[(5,1)],10:[(6,1)],11:[(7,1)],12:[(8,1)],13:[(9,1)],16:[(11,1)],17:[(13,1)],18:[(15,1)],19:[(17,1)],20:[(20,1)],
        23:[(32,1)],24:[(34,1),(37,-1)],25:[(36,1)],26:[(39,1),(42,-1)],27:[(43,1)],28:[(44,1)],31:[(46,1)],32:[(50,1)],
        33:[(52,1)],35:[(53,1)]}
for nombre, E, cur in (('USD', ER_USD, 'usd'), ('MXN', ER_MXN, 'mxn')):
    peor = {}
    for dim in DIM:
        for ln in LINEAS:
            er = [sum(sg*E[f][j] for f, sg in MAPA[ln]) for j in range(NM)]
            s = [sum((VISTAS[dim][cur][mb][ln] or [0.0]*NM)[j] for mb in VISTAS[dim]['miembros']) for j in range(NM)]
            peor[(dim, ln)] = max(abs(a-b) for a, b in zip(er, s))
    mx = max(peor.values())
    print(f'ER {nombre} vs suma de miembros (20 renglones x 4 dimensiones x 12 meses): peor dif = {mx:.6f}')
    assert mx < 0.05, sorted(peor.items(), key=lambda kv: -kv[1])[:5]

# ER USD contra valores vivos de ER en filas tecnicas y de reservas
peor = 0.0; peor_c = None
for f in [5,6,7,8,9,11,12,13,15,16,17,20,22,23,24,25,26,27,28,29,30,32,33,34,36,37,38,39,42,43,44,46,50,52,53,55,56,57,58,66,69,79]:
    for j in range(NM):
        x = CEL['ER'].get((f-1, 5+j), (None, None))[0]
        if isinstance(x, (int, float)):
            dd = abs(x - ER_USD[f][j])
            if dd > peor: peor, peor_c = dd, (f, j, x, ER_USD[f][j])
print(f'ER evaluado (USD) vs valores guardados de ER: peor dif = {peor:.4f} {peor_c}')

# ---------------- columna D (real 2025) y C (2024) de cada vista, por miembro ----------------
def eval_prev(dim, mb, col):
    H = CEL[DIM[dim]['vista']]; A = {r: H.get((r, 0), (None, None))[0] for r in range(8, 44)}
    memo = {}
    def hlookup(hoja, rng, idx):
        a, b = rng.replace('$', '').split(':')
        ca, ra = re.match(r'([A-Z]+)(\d+)', a).groups(); cb, rb = re.match(r'([A-Z]+)(\d+)', b).groups()
        c0 = lambda s: sum((ord(ch)-64)*26**i for i, ch in enumerate(reversed(s))) - 1
        r1, r2, c1, c2 = int(ra)-1, int(rb)-1, c0(ca), c0(cb)
        Hs = CEL[hoja]
        for c in range(c1, c2+1):
            k = Hs.get((r1, c), (None, None))[0]
            if k is not None and clave(k, DIM[dim]['tipo']) == mb:
                v = Hs.get((r1 + int(idx) - 1, c), (None, None))[0]
                return float(v) if isinstance(v, (int, float)) else 0.0
        return None
    def cel(r):
        if r in memo: return memo[r]
        f = H.get((r, col), (None, None))[1]
        if f is None:
            v = H.get((r, col), (None, None))[0]; memo[r] = float(v) if isinstance(v, (int, float)) else 0.0; return memo[r]
        L = 'CD'[col-2]
        def sub_h(m):
            x = hlookup(m.group(1), m.group(2), A[int(m.group(3))-1])
            return 'NAN' if x is None else repr(x)
        f = re.sub(r"HLOOKUP\(\$A\$6,'?([^!',]+)'?!(\$[A-Z]+\$\d+:\$[A-Z]+\$\d+),\$A(\d+),0\)", sub_h, f)
        expr = re.sub(r'SUM\(' + L + r'(\d+):' + L + r'(\d+)\)',
                      lambda k: '(' + '+'.join(f'C({i})' for i in range(int(k.group(1)), int(k.group(2))+1)) + ')', f)
        expr = re.sub(L + r'(\d+)', lambda k: f'C({k.group(1)})', expr)
        def C(n):
            v = cel(n-1); return 0.0 if v is None else v
        try: x = eval(expr, {'C': C, 'NAN': float('nan')})
        except ZeroDivisionError: x = float('nan')
        memo[r] = x; return x
    out = {ln: cel(ln-1) for ln in LINEAS + [38, 39]}
    return {k: (None if (v is None or (isinstance(v, float) and math.isnan(v))) else v) for k, v in out.items()}

for dim in DIM:
    VISTAS[dim]['real25'] = {mb: eval_prev(dim, mb, 3) for mb in VISTAS[dim]['miembros']}
    VISTAS[dim]['real24'] = {mb: eval_prev(dim, mb, 2) for mb in VISTAS[dim]['miembros']}
    # cruce contra la vista viva (miembro seleccionado)
    H = CEL[DIM[dim]['vista']]; sel = clave(H.get((5, 0), (None, None))[0], DIM[dim]['tipo'])
    peor = 0.0
    for ln in LINEAS:
        for col, k in ((2, 'real24'), (3, 'real25')):
            x = H.get((ln-1, col), (None, None))[0]
            mine = VISTAS[dim][k][sel].get(ln)
            if isinstance(x, (int, float)) and mine is not None: peor = max(peor, abs(x - mine))
    print(f'  {DIM[dim]["vista"]} columnas C/D (2024/2025) evaluadas vs celdas vivas A6={sel!r}: peor dif = {peor:.6f}')

pickle.dump(dict(VISTAS=VISTAS, ER_MXN=ER_MXN, ER_USD=ER_USD, TC=TC, TASA_CG=TASA_CG, TASA_RO=TASA_RO,
                 XEVCAT=XEVCAT, LINEAS=LINEAS, MESES=MESES), open('datos05.pkl', 'wb'))
print('datos05.pkl listo')
