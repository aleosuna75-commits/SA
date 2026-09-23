from pyxlsb import open_workbook
import pandas as pd, pickle, time, sys
F = sys.argv[1]; OUT = sys.argv[2]
NOM = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z','AA','AB','AC','AD','AE','AF','AG','AH']
t0 = time.time(); recs = []
with open_workbook(F).get_sheet('CtaMens') as sh:
    for i, row in enumerate(sh.rows()):
        if i < 3: continue
        d = {}
        for c in row:
            if c.c < len(NOM) and c.v is not None: d[NOM[c.c]] = c.v
        if d: d['_fila'] = i + 1; recs.append(d)
df = pd.DataFrame(recs)
pickle.dump(df, open(OUT, 'wb'))
print(F, 'filas', len(df), f'{time.time()-t0:.0f}s', 'columnas', list(df.columns))
