# -*- coding: utf-8 -*-
"""Evalua cada renglon de las vistas ER_ram/ER_ln/ER_reg/ER_tre para cada miembro,
mes a mes acumulado, con la misma formula de la vista. Valida contra la vista viva."""
import pickle, numpy as np, pandas as pd

d   = pickle.load(open('ctamens_full.pkl','rb'))
REF = pickle.load(open('celdas_ref.pkl','rb'))
MESES = list(range(202701, 202713)); NM = 12
XEVCAT = float(REF['Inicio'].get((12,2)) or 0.0)          # Inicio!C13
TASA_CG = [float(REF['Parametros'].get((9,5+j)) or 0.0) for j in range(NM)]   # Parámetros!F10:Q10
RES = REF['2_Reservas']
def rv(r0, c0):
    v = RES.get((r0, c0), (None, None))[0]
    return float(v) if isinstance(v, (int, float)) else 0.0

# ---- dimensiones ----
DIM = {
 'RAMO':  dict(vista='ER_ram', col='R_ramo', key_col=20, tipo='texto',
               t12=[(65,78)], t13=[(84,97)], t18=[(103,116)], t25=[(121,134)]),
 'LN':    dict(vista='ER_ln',  col='C_ln',   key_col=21, tipo='texto',
               t12=[(6,13)],  t13=[(18,25)],  t18=[(31,38)],  t25=[(45,52)]),
 'REGION':dict(vista='ER_reg', col='E_reg',  key_col=21, tipo='texto',
               t12=[(147,152),(169,174)], t13=[(158,163),(180,185)], t18=[(191,196)], t25=[(203,208)]),
 'TREA':  dict(vista='ER_tre', col='L_tre',  key_col=21, tipo='numero',
               t12=[(220,222),(236,238)], t13=[(228,230),(244,246)], t18=[(252,254)], t25=[(261,263)]),
}
LINEAS = [9,10,11,12,13,16,17,18,19,20,23,24,25,26,27,28,31,32,33,35]
NOMBRE = {9:'Prima Tomada',10:'Prima Retrocedida',11:'Prima Retenida',12:'Variación Rva. de Primas s/Prima Tomada',
 13:'Variación Rva. de Primas s/Prima Retenida',16:'Prima Devengada',17:'Siniestros Ocurridos',18:'I.B.N.R.',
 19:'Costos de Adquisición',20:'RESULTADO TÉCNICO TOTAL',23:'Prima Neta Devengada',24:'Siniestros Netos Ocurridos',
 25:'I.B.N.R. (neto)',26:'Costos de Adquisición (neto)',27:'Costos Protecciones XL',28:'RESULTADO TÉCNICO A RETENCIÓN',
 31:'Gastos Generales',32:'(-) Contribución a los Gastos por Retrocesión',33:'TOTAL COSTOS DE OPERACIÓN',35:'RESULTADO DE OPERACIÓN'}
# renglon de ER equivalente: lista de (fila_excel, signo)
ER_MAP = {9:[(5,1)],10:[(6,1)],11:[(7,1)],12:[(8,1)],13:[(9,1)],16:[(11,1)],17:[(13,1)],18:[(15,1)],19:[(17,1)],20:[(20,1)],
          23:[(32,1)],24:[(34,1),(37,-1)],25:[(36,1)],26:[(39,1),(42,-1)],27:[(43,1)],28:[(44,1)],31:[(46,1)],32:[(50,1)],
          33:[(52,1)],35:[(53,1)]}
ER_NOM = {5:'PRIMA EMITIDA',6:'(-) PRIMA CEDIDA / RETROCEDIDA',7:'PRIMA RETENIDA',8:'Variación Rva.de Primas s/Prima Tomada',
 9:'Variación Rva.de Primas s/Prima Retenida',11:'PRIMA DEVENGADA',13:'SINIESTROS Y RECLAMACIONES TOMADOS',15:'SONR',
 17:'COMISIONES DIRECTOS Y TOMADOS',20:'RESULTADO TÉCNICO BRUTO',32:'PRIMA A RETENCIÓN DEVENGADA',34:'SINIESTROS Y RECLAMACIONES TOMADOS',
 37:'(-) SINIESTROS Y RECLAMACIONES RECUPERADOS',36:'SONR (neto)',39:'COMISIONES DIRECTOS Y TOMADOS',42:'(-) COMISIONES CEDIDAS',
 43:'COSTOS PROTECCIONES XL',44:'RESULTADO TÉCNICO A RETENCIÓN',46:'GASTOS GENERALES',50:'(-) CONTRIBUCIÓN A LOS GASTOS POR RETROCESIÓN',
 52:'(-) GASTOS DE OPERACIÓN',53:'RESULTADO DE OPERACIÓN'}

def tabla_keys(bloques, key_col, tipo):
    out = []
    for r1, r2 in bloques[:1]:
        for r in range(r1, r2+1):
            k = RES.get((r, key_col), (None,None))[0]
            if k is None: continue
            out.append(float(k) if tipo=='numero' else str(k))
    return out

def fila_en_tabla(bloques, key_col, tipo, miembro):
    """filas 0-based (una por bloque) donde esta el miembro; None si no esta."""
    filas = []
    for r1, r2 in bloques:
        hit = None
        for r in range(r1, r2+1):
            k = RES.get((r, key_col), (None,None))[0]
            if k is None: continue
            k = float(k) if tipo=='numero' else str(k)
            if k == miembro: hit = r; break
        filas.append(hit)
    return filas

def acum(x): return list(np.cumsum(x))

def evaluar(dim, miembro):
    cfg = DIM[dim]; col = cfg['col']
    sub = d[d[col] == miembro]
    def S(campo, cta=None):
        s = sub if cta is None else sub[sub.B_cta == str(cta)]
        g = s.groupby('A_mes')[campo].sum()
        return [float(g.get(m, 0.0)) for m in MESES]
    m = {}
    m[9]  = acum([-v for v in S('Q_monto',61)])
    m[10] = acum([-v for v in S('W_ced',61)])
    m[11] = [a-b for a,b in zip(m[9],m[10])]
    def reserva(bloques):
        filas = fila_en_tabla(bloques, cfg['key_col'], cfg['tipo'], miembro)
        if all(f is None for f in filas): return None, filas
        mens = [sum(rv(f, 22+j) for f in filas if f is not None) for j in range(NM)]
        return acum(mens), filas
    m[12], f12 = reserva(cfg['t12']); m[13], f13 = reserva(cfg['t13'])
    m[18], f18 = reserva(cfg['t18']); m[25], f25 = reserva(cfg['t25'])
    z = lambda v: v if v is not None else [0.0]*NM
    m[16] = [a-b for a,b in zip(m[9], z(m[12]))]
    q54, ac, ad = S('Q_monto',54), S('AC_evcat'), S('AD_attcat')
    m[17] = acum([a + b*XEVCAT + c for a,b,c in zip(q54, ac, ad)])
    m[19] = acum(S('Q_monto',53))
    m[20] = [a-(b+c+e) for a,b,c,e in zip(m[16], m[17], z(m[18]), m[19])]
    m[23] = [a-b for a,b in zip(m[11], z(m[13]))]
    w54, ae, ab = S('W_ced',54), S('AE_sincatced'), S('AB_recu')
    m[24] = acum([(a + b*XEVCAT + c) - (w + e - r*XEVCAT) for a,b,c,w,e,r in zip(q54,ac,ad,w54,ae,ab)])
    m[26] = acum([a-b for a,b in zip(S('Q_monto',53), S('W_ced',53))])
    m[27] = acum(S('AA_xl',61))
    m[28] = [a-(b+c+e+f) for a,b,c,e,f in zip(m[23], m[24], z(m[25]), m[26], m[27])]
    m[31] = acum(S('AF_gtos',61))
    m[32] = [a*t for a,t in zip(m[10], TASA_CG)]
    m[33] = [a-b for a,b in zip(m[31], m[32])]
    m[35] = [a-b for a,b in zip(m[28], m[33])]
    filas_res = {12:f12, 13:f13, 18:f18, 25:f25}
    return m, filas_res

# ---- universo de miembros por dimension ----
OUT = {}
for dim, cfg in DIM.items():
    keys = tabla_keys(cfg['t12'], cfg['key_col'], cfg['tipo'])
    reales = d[cfg['col']].dropna().unique().tolist()
    reales = [float(x) if cfg['tipo']=='numero' else str(x) for x in reales]
    extra = sorted([x for x in set(reales) if x not in keys], key=str)
    miembros = keys + extra
    filas_cta = d[cfg['col']].value_counts().to_dict()
    res = {}
    for mb in miembros:
        m, fr = evaluar(dim, mb)
        res[mb] = dict(lineas=m, filas_reserva=fr, en_tabla=(mb in keys), en_ctamens=(mb in reales),
                       n_ctamens=int(filas_cta.get(mb, 0)))
    OUT[dim] = dict(miembros=miembros, res=res, vista=cfg['vista'], col=cfg['col'], tipo=cfg['tipo'],
                    t12=cfg['t12'], t13=cfg['t13'], t18=cfg['t18'], t25=cfg['t25'], key_col=cfg['key_col'])

# ---- lado ER (cacheado) ----
ER = REF['ER']
def er_val(fila_excel, j): 
    v = ER.get((fila_excel-1, 5+j)); return float(v) if isinstance(v,(int,float)) else 0.0
ERL = {ln: [sum(sg*er_val(f, j) for f, sg in ER_MAP[ln]) for j in range(NM)] for ln in LINEAS}

pickle.dump(dict(OUT=OUT, ERL=ERL, LINEAS=LINEAS, NOMBRE=NOMBRE, ER_MAP=ER_MAP, ER_NOM=ER_NOM,
                 XEVCAT=XEVCAT, TASA_CG=TASA_CG, MESES=MESES), open('motor.pkl','wb'))

# ---- validacion contra la vista viva ----
print('=== VALIDACION: motor vs vista viva (todas las lineas x 12 meses) ===')
SEL = {'RAMO':'Vida','LN':'LN04001','REGION':'R06','TREA':3.0}
peor_total = 0.0
for dim, mb in SEL.items():
    vista = REF[DIM[dim]['vista']]; m = OUT[dim]['res'][mb]['lineas']; peor = 0.0; peor_cel = ''
    for ln in LINEAS:
        for j in range(NM):
            ref = vista.get((ln-1, 4+j))
            if not isinstance(ref,(int,float)): continue
            mine = m[ln][j] if m[ln] is not None else 0.0
            dif = abs(mine-ref)
            if dif > peor: peor, peor_cel = dif, f'fila {ln} mes {j+1}: motor={mine:,.2f} vista={ref:,.2f}'
    peor_total = max(peor_total, peor)
    print(f'  {DIM[dim]["vista"]:<7} A6={mb!s:<8} peor desviacion = {peor:.6f}   {peor_cel if peor>0.005 else ""}')
print(f'PEOR DESVIACION GLOBAL: {peor_total:.6f}')

print('\n=== SUMA DE MIEMBROS vs ER (diciembre) ===')
for dim in DIM:
    print(f'--- {dim}  ({len(OUT[dim]["miembros"])} miembros: {OUT[dim]["miembros"]})')
    for ln in LINEAS:
        s = sum((OUT[dim]['res'][mb]['lineas'][ln] or [0]*NM)[11] for mb in OUT[dim]['miembros'])
        e = ERL[ln][11]
        flag = '' if abs(s-e) < 0.005 else '  <-- NO CUADRA'
        print(f'   {ln:>2} {NOMBRE[ln][:42]:<42} suma={s:>18,.2f}  ER={e:>18,.2f}  dif={s-e:>16,.2f}{flag}')
