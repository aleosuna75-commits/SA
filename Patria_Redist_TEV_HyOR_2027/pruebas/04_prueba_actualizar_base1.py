# -*- coding: utf-8 -*-
"""
Pruebas de 0a_Actualizar_Base1.py con datos sintéticos.
Uso: python 04_prueba_actualizar_base1.py <carpeta_vacia_de_prueba>

Construye una "verdad" mensual por negocio y ramo; de ella salen (a) la Base_1 previa (2022-01 a 2026-06, formato Base_1,
DescRamo en mayúsculas) y (b) un extracto SAP de reales (2026-04 a 2026-09, signo SAP, cuentas 61/53/54 más cuentas ajenas),
con 3 meses de traslape. Corre casos que deben pasar y casos que deben detenerse.
"""
import os
import subprocess
import sys

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(AQUI, "..", "0a_Actualizar_Base1.py")
REDIST = os.path.join(AQUI, "..", "0_Redistribucion_TEV_HyOR.py")
T = os.path.abspath(sys.argv[1])
os.makedirs(T, exist_ok=True)
rng = np.random.default_rng(7)

CEBE = {"A073000000": ("Terremoto", 73, "TERREMOTO"), "A071000000": ("HyORH", 71, "HYORH"), "A011000000": ("Incendio", 11, "INCENDIO")}
negocios = [(1, 40, 16, "LN04001"), (1, 264, 19, "LN04001"), (2, 85, 4, "LN04002"), (3, 500, None, "LN04001"), (1, 32, 71, "LN04002")]
split73 = {0: 0.6, 1: 0.55, 2: 0.7, 3: 0.5, 4: 0.65}
filas = []
for i, (tr, ced, cto, ln) in enumerate(negocios):
    for anio in range(2022, 2027):
        for mes in range(1, 13):
            if (anio, mes) > (2026, 9):
                continue
            base = 1000 * (i + 1) * (1 + 0.05 * (anio - 2022)) * (1 + 0.1 * rng.random())
            for cebe, frac in [("A073000000", split73[i]), ("A071000000", 1 - split73[i]), ("A011000000", 0.3)]:
                pma = round(base * frac, 2)
                filas.append(dict(TR=tr, CED=ced, CTO=cto, LN=ln, CEBE=cebe, REG="R01", SUSC=anio, ANIO=anio, MES=mes,
                                  PmaTom=pma, CosTom=round(pma * 0.12, 2), SinTom=round(pma * 0.3, 2)))
verdad = pd.DataFrame(filas)


def llave(r):
    return f"{r.TR}-{r.CED}-{0 if pd.isna(r.CTO) else int(r.CTO)}-{r.LN}"


# Base_1 previa (hasta 2026-06)
p = verdad[(verdad.ANIO * 100 + verdad.MES) <= 202606].copy()
prev = pd.DataFrame({
    "LLAVE": p.apply(llave, axis=1), "DescRamo": p.CEBE.map(lambda c: CEBE[c][2]), "Ramo": p.CEBE.map(lambda c: CEBE[c][1]),
    "Territorio": "MEX", "FUNCAREA_2": p.LN.map({"LN04001": "Daños Nacional", "LN04002": "Daños Internacional"}),
    "AñoCont": p.ANIO, "MesCont": p.MES, "Susc": p.SUSC, "TipoRea": p.TR,
    "PmaTom": p.PmaTom, "PmaRet": (p.PmaTom * 0.8).round(2), "SinTom": p.SinTom, "SinRet": (p.SinTom * 0.8).round(2),
    "CosTom": p.CosTom, "CosRet": (p.CosTom * 0.8).round(2)})
prev.to_excel(os.path.join(T, "Base_1.xlsx"), index=False)

# Extracto SAP de reales (2026-04 a 2026-09)
s = verdad[(verdad.ANIO * 100 + verdad.MES) >= 202604].copy()
sap = []
for gl, met, sig in [("6108010000", "PmaTom", -1), ("5301010000", "CosTom", 1), ("5401010000", "SinTom", 1)]:
    sap.append(pd.DataFrame({"/ERP/GL_ACCT": gl, "/ERP/CATEGORY": "REAL01", "/ERP/COMPCODE": "RPAT", "0CURRENCY": "MXN",
                             "/ERP/FUNCAREA": s.LN, "/ERP/PROFTCTR": s.CEBE, "ZCONTRATO": s.CTO, "ZTIPOREAS": s.TR, "ZCEDENTE": s.CED,
                             "ZREGIONRP": s.REG, "ZSUSCYEAR": s.SUSC, "0FISCVARNT": "K4",
                             "0CALMONTH": (s.ANIO * 100 + s.MES).astype(str), "0FISCPER": (s.ANIO * 1000 + s.MES).astype(str),
                             "/ERP/AMOUNT": (s[met] * sig).round(2)}))
sapdf = pd.concat(sap, ignore_index=True)
ajena = sapdf.head(20).copy(); ajena["/ERP/GL_ACCT"] = "5101010000"  # cuenta ajena: debe quedar fuera y reportada
sapdf = pd.concat([sapdf, ajena], ignore_index=True)
# mitad de filas partidas en dos (el grano SAP es más fino que la Base_1): debe agregarse sin cambiar totales
mitad = sapdf.sample(frac=0.3, random_state=1).copy(); mitad["/ERP/AMOUNT"] = 0.0
sapdf = pd.concat([sapdf, mitad], ignore_index=True)
sapdf.to_csv(os.path.join(T, "Real_2026.csv"), index=False)

pd.DataFrame({"CeBe": list(CEBE), "Ramo": [v[1] for v in CEBE.values()], "Ramo2": [v[1] for v in CEBE.values()],
              "RamoN": [v[0] for v in CEBE.values()]}).to_csv(os.path.join(T, "Subramo.csv"), index=False)
pd.DataFrame({"TerrSAP": ["R01"], "Territorio": ["MEX"]}).to_csv(os.path.join(T, "Pais.csv"), index=False)

esperado_final = (verdad.groupby(["ANIO"])[["PmaTom", "CosTom", "SinTom"]].sum())


def correr(nombre, extra, esperado_ok, nueva=None, contiene=None):
    out = os.path.join(T, "out_" + nombre)
    cmd = [sys.executable, SCRIPT, "--previa", os.path.join(T, "Base_1.xlsx"), "--nueva", *(nueva or [os.path.join(T, "Real_2026.csv")]),
           "--subramo", os.path.join(T, "Subramo.csv"), "--pais", os.path.join(T, "Pais.csv"),
           "--salida-csv", os.path.join(out, "Hist_Real_LLAVE_Ramo.csv"), "--salida-xlsx", os.path.join(out, "Base_1_Actualizada.xlsx"),
           "--out-dir", out] + extra
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    txt = r.stdout + r.stderr
    ok = (r.returncode == 0) == esperado_ok and (contiene is None or contiene in txt)
    print(f"[{'OK' if ok else 'FALLA'}] {nombre} (rc={r.returncode}, esperado_ok={esperado_ok})" + (f" | esperado: {contiene}" if contiene else ""))
    if not ok:
        print("\n".join("      " + x for x in txt.splitlines()[-25:]))
    return ok, out


res = []
ok, out = correr("a01_sap_ok", [], True)
res.append(ok)
if ok:
    fin = pd.read_csv(os.path.join(out, "Hist_Real_LLAVE_Ramo.csv"))
    got = fin.groupby("AñoCont")[["PmaTom", "CosTom", "SinTom"]].sum()
    dif = (got - esperado_final.reindex(got.index)).abs().max().max()
    meses26 = fin[fin["AñoCont"] == 2026]["MesCont"].nunique()
    nuevos = fin[(fin["AñoCont"] == 2026) & (fin["MesCont"] >= 7)]
    chk = {"dif_vs_verdad": dif < 0.05, "meses_2026=9": meses26 == 9, "Ramo aprendido": nuevos["Ramo"].notna().all(),
           "FUNCAREA_2 aprendida": nuevos["FUNCAREA_2"].notna().all(), "DescRamo ortografía previa": set(nuevos["DescRamo"]) <= {"TERREMOTO", "HYORH", "INCENDIO"},
           "Territorio por Pais": (nuevos["Territorio"] == "MEX").all(), "PmaRet vacía (no se inventa)": nuevos["PmaRet"].isna().all(),
           "LLAVE contrato nulo = 0": "3-500-0-LN04001" in set(nuevos["LLAVE"]), "xlsx escrito": os.path.isfile(os.path.join(out, "Base_1_Actualizada.xlsx"))}
    for k, v in chk.items():
        print(f"      {'ok ' if v else 'MAL'} {k}")
    res.append(all(chk.values()))
    # integración: la redistribución lee la base actualizada con detalle mensual
    ppto_dir = os.path.join(T, "redist"); os.makedirs(ppto_dir, exist_ok=True)
    pp = []
    for (tr, ced, cto, ln) in negocios:
        for mes in range(1, 13):
            pp.append({"/ERP/GL_ACCT": 6108010000, "/ERP/FUNCAREA": ln, "/ERP/PROFTCTR": "A071000000", "ZCONTRATO": cto, "ZTIPOREAS": tr,
                       "ZCEDENTE": ced, "ZREGIONRP": "R01", "ZSUSCYEAR": 2027, "0FISCYEAR": 2027, "0CALMONTH": 202700 + mes, "/ERP/AMOUNT": -1000.0})
    pd.DataFrame(pp).to_csv(os.path.join(ppto_dir, "PptoTecnico2027.csv"), index=False)
    r = subprocess.run([sys.executable, REDIST, "--ppto", os.path.join(ppto_dir, "PptoTecnico2027.csv"), "--hist", os.path.join(out, "Hist_Real_LLAVE_Ramo.csv"),
                        "--out-dir", os.path.join(ppto_dir, "out"), "--salida", os.path.join(ppto_dir, "PptoTecnico2027_Red.csv"), "--dry-run",
                        "--subramo", "", "--pais", "", "--cesion", "", "--cesionpi", "", "--cesion-hist", "", "--matxl", "", "--dncostoxl", "",
                        "--dnrecup", "", "--evcat", "", "--attritional", "", "--pesos", "", "--td", "", "--layout", ""],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    t = r.stdout + r.stderr
    integ = r.returncode == 0 and "con detalle mensual: True" in t
    print(f"[{'OK' if integ else 'FALLA'}] a02_redistribucion_lee_base_actualizada (rc={r.returncode})")
    if not integ:
        print("\n".join("      " + x for x in t.splitlines()[-20:]))
    res.append(integ)

# sin traslape: el extracto SAP sólo trae 2026-07 a 2026-09
s2 = sapdf[sapdf["0CALMONTH"].astype(int) >= 202607]
s2.to_csv(os.path.join(T, "Real_sin_traslape.csv"), index=False)
res.append(correr("a03_sin_traslape_detiene", [], False, [os.path.join(T, "Real_sin_traslape.csv")], "traslape")[0])
res.append(correr("a04_sin_traslape_justificado", ["--sin-traslape", "Extracto validado contra cierre contable 2026-06"], True, [os.path.join(T, "Real_sin_traslape.csv")])[0])

# signo de comisiones invertido en el mapa: el traslape lo detecta y lo corrige
pd.DataFrame({"GL": ["61", "53", "54"], "METRICA": ["PmaTom", "CosTom", "SinTom"], "SIGNO": [-1, -1, 1]}).to_csv(os.path.join(T, "mapa_gl.csv"), index=False)
res.append(correr("a05_signo_corregido_por_traslape", ["--mapa-gl", os.path.join(T, "mapa_gl.csv")], True, None, "invertido por evidencia del traslape")[0])
# signo explícito del usuario equivocado: no se corrige, se detiene
res.append(correr("a06_signo_usuario_mal_detiene", ["--signo", "CosTom=-1"], False, None, "no reproduce")[0])

# categorías mezcladas
extra_pres = sapdf.head(50).copy(); extra_pres["/ERP/CATEGORY"] = "PRES01"  # filas de presupuesto agregadas a los reales
mix = pd.concat([sapdf, extra_pres], ignore_index=True)
mix.to_csv(os.path.join(T, "Real_mix.csv"), index=False)
res.append(correr("a07_categorias_mezcladas_detiene", [], False, [os.path.join(T, "Real_mix.csv")], "más de una categoría")[0])
res.append(correr("a08_categorias_con_filtro", ["--filtro", "/ERP/CATEGORY=REAL01"], True, [os.path.join(T, "Real_mix.csv")])[0])

# CeBe desconocido
unk = sapdf.copy(); unk.loc[unk.index[:5], "/ERP/PROFTCTR"] = "A099000000"
unk.to_csv(os.path.join(T, "Real_cebe.csv"), index=False)
res.append(correr("a09_cebe_sin_ramo_detiene", [], False, [os.path.join(T, "Real_cebe.csv")], "sin DescRamo")[0])

# traslape que no cuadra en Terremoto (+5 % en 2026-05)
bad = sapdf.copy()
m = (bad["0CALMONTH"] == "202605") & (bad["/ERP/PROFTCTR"] == "A073000000") & (bad["/ERP/GL_ACCT"] == "6108010000")
bad.loc[m, "/ERP/AMOUNT"] *= 1.5
bad.to_csv(os.path.join(T, "Real_bad.csv"), index=False)
ok_bad, out_bad = correr("a10_traslape_no_cuadra_detiene", [], False, [os.path.join(T, "Real_bad.csv")], "TERREMOTO")
res.append(ok_bad and not os.path.isfile(os.path.join(out_bad, "Hist_Real_LLAVE_Ramo.csv"))
           and any(f.endswith("_CONTROL_FALLIDO.xlsx") for f in os.listdir(out_bad)))
res.append(correr("a11_traslape_aceptado_con_justificacion", ["--aceptar-traslape", "Ajuste contable de mayo documentado en ticket X"], True, [os.path.join(T, "Real_bad.csv")])[0])

# formato Base_1 como información nueva
nb = prev[(prev["AñoCont"] == 2026) & (prev["MesCont"] >= 5)].copy()
nb.to_excel(os.path.join(T, "Nueva_formato_base1.xlsx"), index=False)
res.append(correr("a12_nueva_formato_base1", [], True, [os.path.join(T, "Nueva_formato_base1.xlsx")])[0])

# dos archivos con los mismos periodos
res.append(correr("a13_periodos_duplicados_detiene", [], False, [os.path.join(T, "Real_2026.csv"), os.path.join(T, "Real_bad.csv")], "mismos periodos")[0])

# sólo 0FISCPER (sin 0CALMONTH)
sapdf.drop(columns=["0CALMONTH"]).to_csv(os.path.join(T, "Real_fiscper.csv"), index=False)
res.append(correr("a14_periodo_desde_fiscper", [], True, [os.path.join(T, "Real_fiscper.csv")])[0])

# dry-run no escribe
ok_dr, out_dr = correr("a15_dry_run", ["--dry-run"], True)
res.append(ok_dr and not os.path.isfile(os.path.join(out_dr, "Hist_Real_LLAVE_Ramo.csv")))

# salida = previa
r = subprocess.run([sys.executable, SCRIPT, "--previa", os.path.join(T, "Base_1.xlsx"), "--nueva", os.path.join(T, "Real_2026.csv"),
                    "--salida-xlsx", os.path.join(T, "Base_1.xlsx"), "--out-dir", os.path.join(T, "out_a16")], capture_output=True, text=True)
res.append(r.returncode != 0)
print(f"[{'OK' if r.returncode != 0 else 'FALLA'}] a16_salida_igual_previa_detiene")

# presupuesto en lugar de reales
pres = sapdf.copy(); pres["/ERP/CATEGORY"] = "PRES01"
pres.to_csv(os.path.join(T, "Real_pres.csv"), index=False)
res.append(correr("a17_presupuesto_detiene", [], False, [os.path.join(T, "Real_pres.csv")], "presupuesto")[0])

# Base_1 guardada antes de sus últimos periodos (como una Base_1 de dic-2025 con meses 2026): esos meses se excluyen
import shutil, time
fut = os.path.join(T, "Base_1_fut.xlsx"); shutil.copy(os.path.join(T, "Base_1.xlsx"), fut)
ts_ = time.mktime((2026, 4, 30, 12, 0, 0, 0, 0, -1)); os.utime(fut, (ts_, ts_))
out = os.path.join(T, "out_a18")
r = subprocess.run([sys.executable, SCRIPT, "--previa", fut, "--nueva", os.path.join(T, "Real_2026.csv"), "--subramo", os.path.join(T, "Subramo.csv"),
                    "--pais", os.path.join(T, "Pais.csv"), "--salida-csv", os.path.join(out, "h.csv"), "--out-dir", out, "--sin-xlsx"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
okf = r.returncode == 0 and "se EXCLUYEN de la historia" in r.stdout
if okf:
    fin = pd.read_csv(os.path.join(out, "h.csv"))
    got = fin.groupby("AñoCont")[["PmaTom"]].sum()["PmaTom"]
    okf = abs(got.loc[2026] - esperado_final.loc[2026, "PmaTom"]) < 0.05  # mayo-junio vienen de la nueva, no se duplican
print(f"[{'OK' if okf else 'FALLA'}] a18_previa_con_periodos_posteriores_a_su_fecha")
if not okf:
    print((r.stdout + r.stderr)[-2000:])
res.append(okf)
# la redistribución excluye años base posteriores a la fecha del histórico
hist_fut = os.path.join(T, "hist_fut.xlsx"); shutil.copy(os.path.join(T, "Base_1.xlsx"), hist_fut)
ts_ = time.mktime((2025, 12, 30, 12, 0, 0, 0, 0, -1)); os.utime(hist_fut, (ts_, ts_))
ppto_dir = os.path.join(T, "redist")
r = subprocess.run([sys.executable, REDIST, "--ppto", os.path.join(ppto_dir, "PptoTecnico2027.csv"), "--hist", hist_fut,
                    "--out-dir", os.path.join(ppto_dir, "out_fut"), "--dry-run",
                    "--subramo", "", "--pais", "", "--cesion", "", "--cesionpi", "", "--cesion-hist", "", "--matxl", "", "--dncostoxl", "",
                    "--dnrecup", "", "--evcat", "", "--attritional", "", "--pesos", "", "--td", "", "--layout", ""],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
okr = r.returncode == 0 and "no pueden ser reales y NO se usan" in r.stdout and "2 últimos años reales completos, >= 8 meses en la base): [2024, 2025]" in r.stdout
print(f"[{'OK' if okr else 'FALLA'}] a19_redistribucion_excluye_anios_posteriores_al_archivo")
if not okr:
    print((r.stdout + r.stderr)[-2000:])
res.append(okr)

print(f"\n{sum(res)}/{len(res)} verificaciones OK")
sys.exit(0 if all(res) else 1)
