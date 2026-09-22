import sys, fmla, dump, pickle
from biff import colrow, sheet_map
path='FCST.xlsb'
ctx=fmla.Ctx(path); S=dump.sst(path)
SM={n:p for n,p in sheet_map(path)}
name=sys.argv[1]; lo=int(sys.argv[2]); hi=int(sys.argv[3])
maxc=int(sys.argv[4]) if len(sys.argv)>4 else 20
for r,c,v,f in dump.cells(path,SM[name],ctx,S):
    if not (lo-1<=r<=hi-1) or c>maxc: continue
    if v is None and f is None: continue
    vs=f'{v:,.2f}' if isinstance(v,float) else repr(v)
    print(f'{colrow(r,c):<6} {"F" if f else "c"} {vs:>20}  {f or ""}')
